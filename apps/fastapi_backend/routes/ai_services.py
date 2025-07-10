"""
AI service management routes.
Handles AI pipeline, YOLOX, annotation services, and related functionality.
"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import OUTPUT_DIR, logger
from dependencies import get_ai_orchestrator
from schemas import AIPipelineStartRequest

router = APIRouter()


# AI Pipeline Management
@router.post("/api/ai/pipeline/start")
async def start_ai_pipeline(request: AIPipelineStartRequest):
    """Start the complete AI processing pipeline for a task."""
    try:
        logger.info(f"Starting AI pipeline for task {request.task_id}")
        
        ai_orchestrator = get_ai_orchestrator()
        
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


@router.post("/api/ai/pipeline/{task_id}/stop")
async def stop_ai_pipeline(task_id: str):
    """Stop the AI processing pipeline for a task."""
    try:
        logger.info(f"Stopping AI pipeline for task {task_id}")
        
        ai_orchestrator = get_ai_orchestrator()
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


@router.get("/api/ai/pipeline/{task_id}/status")
async def get_ai_pipeline_status(task_id: str):
    """Get status of the AI processing pipeline for a task."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        status = await ai_orchestrator.get_pipeline_status(task_id)
        return status

    except Exception as e:
        logger.error(f"Error getting AI pipeline status for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline status: {str(e)}")


@router.get("/api/ai/health")
async def get_ai_health():
    """Get detailed health status of all AI services."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        health = await ai_orchestrator.health_check()
        return health

    except Exception as e:
        logger.error(f"Error getting AI services health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get AI health: {str(e)}")


# YOLOX Service Management
@router.get("/api/ai/yolox/services")
async def list_yolox_services():
    """List all YOLOX services."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        services = await ai_orchestrator.yolox_client.list_services()
        return {
            "services": services,
            "count": len(services)
        }

    except Exception as e:
        logger.error(f"Error listing YOLOX services: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list YOLOX services: {str(e)}")


@router.get("/api/ai/yolox/{task_id}/status")
async def get_yolox_service_status(task_id: str):
    """Get status of a specific YOLOX service."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        status = await ai_orchestrator.yolox_client.get_service_status(task_id)
        return status

    except Exception as e:
        logger.error(f"Error getting YOLOX service status for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"YOLOX service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to get YOLOX status: {str(e)}")


@router.post("/api/ai/yolox/{task_id}/stop")
async def stop_yolox_service(task_id: str):
    """Stop a specific YOLOX service."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        result = await ai_orchestrator.yolox_client.stop_service(task_id)
        return result

    except Exception as e:
        logger.error(f"Error stopping YOLOX service for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"YOLOX service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to stop YOLOX service: {str(e)}")


# Annotation Service Endpoints
@router.get("/api/annotation/{task_id}/rtsp_url")
async def get_annotation_rtsp_url(task_id: str):
    """Get the processed RTSP stream URL from annotation service."""
    try:
        # Annotation service outputs to rtsp://localhost:8554/outstream_{task_id}
        processed_rtsp_url = f"rtsp://localhost:8554/outstream_{task_id}"

        return {
            "task_id": task_id,
            "processed_rtsp_url": processed_rtsp_url,
            "original_rtsp_url": f"rtsp://localhost:8554/{task_id}",
            "message": "Processed RTSP stream from annotation service"
        }
    except Exception as e:
        logger.error(f"Error getting annotation RTSP URL for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get annotation RTSP URL: {str(e)}")


@router.get("/api/annotation/{task_id}/videos")
async def get_annotation_videos(task_id: str):
    """Get list of generated video files from annotation service."""
    try:
        video_dir = OUTPUT_DIR / "output_videos" / task_id
        video_files = []

        if video_dir.exists():
            # Find all MP4 files in the task directory
            for video_file in video_dir.glob("*.mp4"):
                file_stat = video_file.stat()
                video_info = {
                    "filename": video_file.name,
                    "path": str(video_file),
                    "size": file_stat.st_size,
                    "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                    "download_url": f"/api/annotation/{task_id}/download/{video_file.name}"
                }
                video_files.append(video_info)

        return {
            "task_id": task_id,
            "video_files": video_files,
            "count": len(video_files),
            "output_directory": str(video_dir)
        }
    except Exception as e:
        logger.error(f"Error getting annotation videos for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get annotation videos: {str(e)}")


@router.get("/api/annotation/{task_id}/download/{filename}")
async def download_annotation_video(task_id: str, filename: str):
    """Download a specific annotation video file."""
    try:
        video_path = OUTPUT_DIR / "output_videos" / task_id / filename

        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")

        # Security check: ensure filename doesn't contain path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        return FileResponse(
            path=str(video_path),
            media_type="video/mp4",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading annotation video {filename} for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: {str(e)}")


@router.get("/api/annotation/{task_id}/status")
async def get_annotation_service_status(task_id: str):
    """Get status of annotation service for a specific task."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        
        # Try to get annotation service status from AI orchestrator
        status = await ai_orchestrator.annotation_client.get_service_status(task_id)

        # Also check for video files
        video_info = await get_annotation_videos(task_id)

        return {
            "task_id": task_id,
            "service_status": status,
            "video_files": video_info["video_files"],
            "video_count": video_info["count"],
            "processed_rtsp_url": f"rtsp://localhost:8554/outstream_{task_id}"
        }
    except Exception as e:
        logger.error(f"Error getting annotation status for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"Annotation service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to get annotation status: {str(e)}")


@router.post("/api/annotation/{task_id}/stop")
async def stop_annotation_service(task_id: str):
    """Stop annotation service for a specific task."""
    try:
        ai_orchestrator = get_ai_orchestrator()
        result = await ai_orchestrator.annotation_client.stop_service(task_id)
        return result
    except Exception as e:
        logger.error(f"Error stopping annotation service for task {task_id}: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=f"Annotation service not found for task {task_id}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to stop annotation service: {str(e)}") 