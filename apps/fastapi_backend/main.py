"""
FastAPI backend for multi-user AI video analysis platform.
"""
import os
import uuid
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from .tasks import process_video_task
from .kafka_controller import KafkaController
from .schemas import TaskResponse, TaskStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="AI Video Analysis Platform", version="1.0.0")

# Global storage
UPLOAD_DIR = Path("/tmp/video_uploads")
OUTPUT_DIR = Path("/tmp/video_outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Task tracking
task_status_db: Dict[str, TaskStatus] = {}

# Initialize Kafka controller
kafka_controller = KafkaController()


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting AI Video Analysis Platform...")
    # TODO: Initialize AI services health check
    # TODO: Verify Kafka connectivity


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down AI Video Analysis Platform...")
    kafka_controller.close()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Video Analysis Platform",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/upload",
            "status": "/status/{task_id}",
            "result": "/result/{task_id}"
        }
    }


@app.post("/upload", response_model=TaskResponse)
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
    allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {allowed_extensions}"
        )
    
    # Generate unique task ID
    task_id = str(uuid.uuid4())
    
    # Save uploaded file
    file_path = UPLOAD_DIR / f"{task_id}{file_ext}"
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved upload file: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")
    
    # Create Kafka topics
    if not kafka_controller.create_topics_for_task(task_id):
        raise HTTPException(status_code=500, detail="Failed to create Kafka topics")
    
    # Initialize task status
    task_status_db[task_id] = TaskStatus(
        task_id=task_id,
        status="initializing",
        progress=0,
        created_at=datetime.utcnow(),
        input_file=str(file_path),
        output_file=None
    )
    
    # Launch background processing
    background_tasks.add_task(
        process_video_task,
        task_id=task_id,
        video_path=str(file_path),
        kafka_controller=kafka_controller,
        status_db=task_status_db
    )
    
    # Return response
    return TaskResponse(
        task_id=task_id,
        message="Task started successfully",
        stream_url=f"rtsp://localhost:8554/{task_id}"
    )


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """
    Get the status of a processing task.
    
    Args:
        task_id: Unique task identifier
        
    Returns:
        Task status information
    """
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


@app.get("/result/{task_id}")
async def get_result(task_id: str):
    """
    Get the output video file for a completed task.
    
    Args:
        task_id: Unique task identifier
        
    Returns:
        Video file or redirect to stream
    """
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
            "stream_url": f"rtsp://localhost:8554/{task_id}"
        }
    )


@app.delete("/task/{task_id}")
async def delete_task(task_id: str, background_tasks: BackgroundTasks):
    """
    Delete a task and clean up resources.
    
    Args:
        task_id: Unique task identifier
        background_tasks: FastAPI background task manager
        
    Returns:
        Deletion confirmation
    """
    if task_id not in task_status_db:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Schedule cleanup
    background_tasks.add_task(
        cleanup_task,
        task_id=task_id,
        kafka_controller=kafka_controller,
        status_db=task_status_db
    )
    
    return {"message": f"Task {task_id} scheduled for deletion"}


async def cleanup_task(task_id: str, kafka_controller: KafkaController, status_db: Dict):
    """Clean up task resources."""
    logger.info(f"Cleaning up task {task_id}")
    
    # Delete Kafka topics
    kafka_controller.delete_topics_for_task(task_id, delay_seconds=0)
    
    # Delete files
    status = status_db.get(task_id)
    if status:
        for file_path in [status.input_file, status.output_file]:
            if file_path and Path(file_path).exists():
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete file {file_path}: {e}")
    
    # Remove from status DB
    status_db.pop(task_id, None)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # TODO: Add actual health checks for Kafka, AI services
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "kafka": "TODO: Check Kafka connection",
            "yolox": "TODO: Check YOLOX service",
            "rtmpose": "TODO: Check RTMPose service",
            "bytetrack": "TODO: Check ByteTrack service",
            "annotation": "TODO: Check Annotation service"
        }
    }