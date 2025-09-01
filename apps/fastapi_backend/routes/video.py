"""
Video processing routes.
Handles video upload, processing, and result retrieval.
"""
import asyncio
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from config import UPLOAD_DIR, ALLOWED_VIDEO_EXTENSIONS, RTSP_BASE_URL, logger
from dependencies import get_kafka_controller, get_rtsp_manager, get_ai_orchestrator, get_mongodb_client
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from models import get_task_status_db, update_task_status
from schemas import TaskResponse, TaskStatus, VideoUploadRecord

from tasks import process_video_task

router = APIRouter()


@router.post("/upload", response_model=TaskResponse)
async def upload_video(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
):
    """
    Upload a video file for processing.
    
    Args:
        file: Video file to process
        background_tasks: FastAPI background task manager
        
    Returns:
        Task information including ID and stream URL
    """
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {ALLOWED_VIDEO_EXTENSIONS}"
        )

    # if filename already exists, replace it
    if (UPLOAD_DIR / file.filename).exists():
        logger.warning(f"File {file.filename} already exists, replacing it.")
        os.remove(UPLOAD_DIR / file.filename)

    # Generate unique task ID
    task_id = str(uuid.uuid4())

    # Save uploaded file
    file_path = UPLOAD_DIR / f"{file.filename}"
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved upload file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Get services
    kafka_controller = get_kafka_controller()
    rtsp_manager = get_rtsp_manager()
    ai_orchestrator = get_ai_orchestrator()
    task_status_db = get_task_status_db()
    mongodb_client = get_mongodb_client()

    # Create Kafka topics
    if not kafka_controller.create_topics_for_task(task_id):
        raise HTTPException(status_code=500, detail="Failed to create Kafka topics")

    # Initialize task status
    task_status = TaskStatus(
        task_id=task_id,
        status="completed",
        progress=0,
        created_at=datetime.utcnow(),
        input_file=str(file_path),
        output_file=None,
        error=None
    )
    update_task_status(task_id, task_status)

    # Save video upload record to MongoDB
    try:
        output_video_path = f"output_videos/annotated_{task_id}.mp4"
        video_record = VideoUploadRecord(
            task_id=task_id,
            filename=file.filename,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            created_at=datetime.utcnow(),
            status="completed",
            output_video_path=output_video_path,
            stream_url=f"{RTSP_BASE_URL}/{task_id}"
        )

        # Save to MongoDB asynchronously (don't fail upload if MongoDB fails)
        save_success = await mongodb_client.save_video_record(video_record)
        if save_success:
            logger.info(f"Video upload record saved to MongoDB for task_id: {task_id}")
        else:
            logger.warning(f"Failed to save video upload record to MongoDB for task_id: {task_id}")

    except Exception as e:
        logger.error(f"Error saving video record to MongoDB: {e}")
        # Continue without failing the upload

    # Create RTSP stream from the uploaded video
    # try:
    #     stream_url = rtsp_manager.create_stream_from_video(task_id, str(file_path))
    #     logger.info(f"Created RTSP stream for task {task_id}: {stream_url}")
    # except Exception as e:
    #     logger.error(f"Failed to create RTSP stream for task {task_id}: {e}")
    #     # Continue without RTSP stream

    asyncio.create_task(
        process_video_task(task_id, file_path, kafka_controller, task_status)
    )
    logger.info(f"Processed upload file: {file_path}")
    # Start AI pipeline for the task
    try:
        logger.info(f"Starting AI pipeline for uploaded video task {task_id}")
        ai_result = await ai_orchestrator.start_pipeline(task_id)
        if ai_result["success"]:
            logger.info(f"AI pipeline started successfully for task {task_id}")
        else:
            logger.warning(f"AI pipeline failed to start for task {task_id}: {ai_result.get('errors', [])}")
    except Exception as e:
        logger.error(f"Error starting AI pipeline for task {task_id}: {e}")
    # Don't fail the upload if AI pipeline fails to start

    # Return response
    return TaskResponse(
        task_id=task_id,
        message="Task started successfully",
        stream_url=f"{RTSP_BASE_URL}/{task_id}"
    )


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a processing task.
    
    Args:
        task_id: Unique task identifier
        
    Returns:
        Task status information
    """
    task_status_db = get_task_status_db()

    if task_id not in task_status_db:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task_status_db[task_id]
    return {
        "task_id": task_id,
        "status": status.status,
        "progress": f"{status.progress}%",
        "created_at": status.created_at.isoformat(),
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
        "error": status.error
    }


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    """
    Get the output video file for a completed task.
    
    Args:
        task_id: Unique task identifier
        
    Returns:
        Video file or redirect to stream
    """
    task_status_db = get_task_status_db()

    if task_id not in task_status_db:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task_status_db[task_id]

    if status.status != "completed":
        return JSONResponse(
            status_code=202,
            content={
                "message": "Task not completed yet",
                "status": status.status,
                "progress": f"{status.progress}%"
            }
        )

    if status.output_file and Path(status.output_file).exists():
        return FileResponse(
            path=status.output_file,
            media_type="video/mp4",
            filename=f"output_{task_id}.mp4"
        )

    # If no file, return RTSP stream URL
    return JSONResponse(
        content={
            "message": "Output available via RTSP stream",
            "stream_url": f"{RTSP_BASE_URL}/{task_id}"
        }
    )


@router.get("/records/{task_id}")
async def get_video_record(task_id: str):
    """
    Get video upload record by task_id from MongoDB.
    
    Args:
        task_id: Unique task identifier
        
    Returns:
        Video upload record information
    """
    mongodb_client = get_mongodb_client()

    record = await mongodb_client.get_video_record(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video record not found")

    return record


@router.get("/records")
async def list_video_records(limit: int = 50, skip: int = 0):
    """
    List video upload records with pagination.
    
    Args:
        limit: Maximum number of records to return (default: 50)
        skip: Number of records to skip (default: 0)
        
    Returns:
        List of video upload records
    """
    mongodb_client = get_mongodb_client()

    records = await mongodb_client.list_video_records(limit=limit, skip=skip)
    return {
        "records": records,
        "count": len(records),
        "limit": limit,
        "skip": skip
    }
