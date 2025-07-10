"""
Task management routes.
Handles task listing, deletion, and file management.
"""
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from config import UPLOAD_DIR, KAFKA_TOPIC_CLEANUP_DELAY, logger
from dependencies import get_kafka_controller
from models import get_task_status_db, delete_task_status

router = APIRouter()


@router.get("/api/files")
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


@router.get("/api/tasks")
async def list_tasks():
    """List all tasks and their status."""
    task_status_db = get_task_status_db()
    
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


@router.delete("/task/{task_id}")
async def delete_task(task_id: str, background_tasks: BackgroundTasks):
    """
    Delete a task and clean up resources.
    
    Args:
        task_id: Unique task identifier
        background_tasks: FastAPI background task manager
        
    Returns:
        Deletion confirmation
    """
    task_status_db = get_task_status_db()
    
    if task_id not in task_status_db:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get services
    kafka_controller = get_kafka_controller()

    # Schedule cleanup
    background_tasks.add_task(
        cleanup_task,
        task_id=task_id,
        kafka_controller=kafka_controller
    )

    return {"message": f"Task {task_id} scheduled for deletion"}


async def cleanup_task(task_id: str, kafka_controller):
    """Clean up task resources."""
    logger.info(f"Cleaning up task {task_id}")
    
    task_status_db = get_task_status_db()

    # Delete Kafka topics
    kafka_controller.delete_topics_for_task(task_id, delay_seconds=KAFKA_TOPIC_CLEANUP_DELAY)

    # Delete files
    status = task_status_db.get(task_id)
    if status:
        for file_path in [status.input_file, status.output_file]:
            if file_path and Path(file_path).exists():
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete file {file_path}: {e}")

    # Remove from status DB
    delete_task_status(task_id) 