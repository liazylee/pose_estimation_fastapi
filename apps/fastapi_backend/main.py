"""
FastAPI backend for multi-user AI video analysis platform.
"""
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ai_service_client import AIServiceOrchestrator
from kafka_controller import KafkaController
from schemas import TaskResponse, TaskStatus, AIPipelineStartRequest
from tasks import process_video_task
from video_utils import RTSPStreamManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AI Video Analysis Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "outputs"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Task tracking
task_status_db: Dict[str, TaskStatus] = {}

# Initialize services
kafka_controller = KafkaController()
rtsp_manager = RTSPStreamManager()
ai_orchestrator = AIServiceOrchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Video Analysis Platform...")
    health = await ai_orchestrator.health_check()
    logger.info(f"AI Services health check: {health}")
    yield
    logger.info("Shutting down AI Video Analysis Platform...")
    kafka_controller.close()


app.router.lifespan_context = lifespan


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    html_file = TEMPLATES_DIR / "dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(), status_code=200)
    else:
        return HTMLResponse(
            content="""
            <html>
                <head><title>AI Video Analysis Platform</title></head>
                <body>
                    <h1>AI Video Analysis Platform</h1>
                    <p>Dashboard is being set up...</p>
                    <p>API endpoints:</p>
                    <ul>
                        <li>POST /upload - Upload video file</li>
                        <li>GET /status/{task_id} - Check task status</li>
                        <li>GET /result/{task_id} - Get result</li>
                        <li>GET /health - Health check</li>
                        <li>GET /api/files - List uploaded files</li>
                    </ul>
                </body>
            </html>
            """,
            status_code=200
        )


@app.get("/api")
async def api_root():
    """API root endpoint."""
    return {
        "message": "AI Video Analysis Platform API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/upload",
            "status": "/status/{task_id}",
            "result": "/result/{task_id}",
            "health": "/health",
            "files": "/api/files",
            "tasks": "/api/tasks",
            "streams": "/streams",
            "streams/{task_id}/stop": "/streams/{task_id}/stop",
            "streams/{task_id}/status": "/streams/{task_id}/status",
            # AI Service Management
            "ai_start_pipeline": "/api/ai/pipeline/start",
            "ai_stop_pipeline": "/api/ai/pipeline/{task_id}/stop",
            "ai_pipeline_status": "/api/ai/pipeline/{task_id}/status",
            "ai_health": "/api/ai/health",
            "yolox_services": "/api/ai/yolox/services",
            "yolox_service_status": "/api/ai/yolox/{task_id}/status"
        }
    }


@app.get("/api/files")
async def list_files():
    """List all uploaded files."""
    try:
        files = []
        for file_path in UPLOAD_DIR.glob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@app.get("/api/tasks")
async def list_tasks():
    """List all tasks and their status."""
    tasks = []
    for task_id, status in task_status_db.items():
        tasks.append({
            "task_id": task_id,
            "status": status.status,
            "progress": status.progress,
            "created_at": status.created_at.isoformat(),
            "updated_at": status.updated_at.isoformat() if status.updated_at else None,
            "input_file": Path(status.input_file).name if status.input_file else None,
            "error": status.error
        })
    return {"tasks": tasks, "count": len(tasks)}


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
        output_file=None,
        error=None
    )
    rtsp_url: Optional[str] = None
    # Create RTSP stream from the uploaded video
    try:
        stream_url = rtsp_manager.create_stream_from_video(task_id, str(file_path))
        logger.info(f"Created RTSP stream for task {task_id}: {stream_url}")
    except Exception as e:
        logger.error(f"Failed to create RTSP stream for task {task_id}: {e}")
        # Continue without RTSP stream

    # Launch background processing
    background_tasks.add_task(
        process_video_task,
        task_id=task_id,
        video_path=str(file_path),
        kafka_controller=kafka_controller,
        status_db=task_status_db
    )

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
    kafka_controller.delete_topics_for_task(task_id, delay_seconds=60 * 60)  # 1 hour delay

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
    # Get AI services health
    ai_health = await ai_orchestrator.health_check()

    return {
        "status": "healthy" if ai_health["overall_healthy"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "kafka": "TODO: Check Kafka connection",
            "rtmpose": ai_health["services"].get("rtmpose", {}).get("status", "unknown"),
            "bytetrack": ai_health["services"].get("bytetrack", {}).get("status", "unknown"),
            "annotation": ai_health["services"].get("annotation", {}).get("status", "unknown"),
            "yolox": ai_health["services"].get("yolox", {})
        },
        "ai_services_summary": ai_health
    }


@app.get("/streams")
async def get_active_streams():
    """Get list of active RTSP streams."""
    try:
        active_streams = rtsp_manager.get_active_streams()
        return {
            "active_streams": active_streams,
            "count": len(active_streams)
        }
    except Exception as e:
        logger.error(f"Error getting active streams: {e}")
        raise HTTPException(status_code=500, detail="Failed to get active streams")


@app.post("/streams/{task_id}/stop")
async def stop_stream(task_id: str):
    """Stop an RTSP stream for a specific task."""
    try:
        if not rtsp_manager.is_stream_active(task_id):
            raise HTTPException(status_code=404, detail="Stream not found or not active")

        rtsp_manager.stop_stream(task_id)
        logger.info(f"Stopped RTSP stream for task {task_id}")

        return {"message": f"Stream for task {task_id} stopped successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping stream for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop stream")


@app.get("/streams/{task_id}/status")
async def get_stream_status(task_id: str):
    """Get status of a specific stream."""

    status = rtsp_manager.get_stream_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Stream with task_id {task_id} not found")
    return {
        "task_id": task_id,
        "active": status.get("active", False),
        "rtsp_url": status.get("rtsp_url", None),
        "created_at": status.get("created_at", None),
    }


# AI Service Management Endpoints
@app.post("/api/ai/pipeline/start")
async def start_ai_pipeline(request: AIPipelineStartRequest):
    """Start the complete AI processing pipeline for a task."""

    try:
        logger.info(f"Starting AI pipeline for task {request.task_id}")

        # Start AI services pipeline
        result = await ai_orchestrator.start_pipeline(request.task_id, request.config)

        if result["success"]:
            return {
                "success": True,
                "task_id": request.task_id,
                "message": f"AI pipeline started successfully for task {request.task_id}",
                "services": result["services"]
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to start AI pipeline: {', '.join(result['errors'])}"
            )

    except Exception as e:
        logger.error(f"Error starting AI pipeline for task {request.task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start AI pipeline: {str(e)}")


@app.post("/api/ai/pipeline/{task_id}/stop")
async def stop_ai_pipeline(task_id: str):
    """Stop the AI processing pipeline for a task."""

    try:
        logger.info(f"Stopping AI pipeline for task {task_id}")

        result = await ai_orchestrator.stop_pipeline(task_id)

        if result["success"]:
            return {
                "success": True,
                "task_id": task_id,
                "message": f"AI pipeline stopped successfully for task {task_id}",
                "services": result["services"]
            }
        else:
            return {
                "success": False,
                "task_id": task_id,
                "message": f"Partial failure stopping AI pipeline: {', '.join(result['errors'])}",
                "services": result["services"]
            }

    except Exception as e:
        logger.error(f"Error stopping AI pipeline for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop AI pipeline: {str(e)}")


@app.get("/api/ai/pipeline/{task_id}/status")
async def get_ai_pipeline_status(task_id: str):
    """Get status of the AI processing pipeline for a task."""

    try:
        status = await ai_orchestrator.get_pipeline_status(task_id)
        return status

    except Exception as e:
        logger.error(f"Error getting AI pipeline status for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline status: {str(e)}")


@app.get("/api/ai/health")
async def get_ai_health():
    """Get detailed health status of all AI services."""

    try:
        health = await ai_orchestrator.health_check()
        return health

    except Exception as e:
        logger.error(f"Error getting AI services health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get AI health: {str(e)}")


@app.get("/api/ai/yolox/services")
async def list_yolox_services():
    """List all YOLOX services."""

    try:
        services = await ai_orchestrator.yolox_client.list_services()
        return {
            "services": services,
            "count": len(services)
        }

    except Exception as e:
        logger.error(f"Error listing YOLOX services: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list YOLOX services: {str(e)}")


@app.get("/api/ai/yolox/{task_id}/status")
async def get_yolox_service_status(task_id: str):
    """Get status of a specific YOLOX service."""

    try:
        status = await ai_orchestrator.yolox_client.get_service_status(task_id)
        return status

    except Exception as e:
        logger.error(f"Error getting YOLOX service status for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"YOLOX service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to get YOLOX status: {str(e)}")


@app.post("/api/ai/yolox/{task_id}/stop")
async def stop_yolox_service(task_id: str):
    """Stop a specific YOLOX service."""

    try:
        result = await ai_orchestrator.yolox_client.stop_service(task_id)
        return result

    except Exception as e:
        logger.error(f"Error stopping YOLOX service for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"YOLOX service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to stop YOLOX service: {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Analysis controller backend")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
