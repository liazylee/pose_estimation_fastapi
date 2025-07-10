"""
RTSP stream management routes.
Handles stream status, control, and monitoring.
"""
from config import logger
from dependencies import get_rtsp_manager
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/streams")
async def get_active_streams():
    """Get list of active RTSP streams."""
    try:
        rtsp_manager = get_rtsp_manager()
        active_streams = rtsp_manager.get_active_streams()

        return {
            "active_streams": active_streams,
            "count": len(active_streams)
        }
    except Exception as e:
        logger.error(f"Error getting active streams: {e}")
        raise HTTPException(status_code=500, detail="Failed to get active streams")


@router.post("/streams/{task_id}/stop")
async def stop_stream(task_id: str):
    """Stop an RTSP stream for a specific task."""
    try:
        rtsp_manager = get_rtsp_manager()

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


@router.get("/streams/{task_id}/status")
async def get_stream_status(task_id: str):
    """Get status of a specific stream."""
    rtsp_manager = get_rtsp_manager()

    status = rtsp_manager.get_stream_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Stream with task_id {task_id} not found")

    return {
        "task_id": task_id,
        "active": status.get("active", False),
        "rtsp_url": status.get("rtsp_url", None),
        "annotations_rtsp_url": f'rtsp://localhost:8554/outstream_{task_id}',
        "created_at": status.get("created_at", None),
    }
