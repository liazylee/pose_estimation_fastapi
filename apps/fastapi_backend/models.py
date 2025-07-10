"""
Data models and global state management.
"""
from typing import Dict
from schemas import TaskStatus

# Global task status database
task_status_db: Dict[str, TaskStatus] = {}

def get_task_status_db() -> Dict[str, TaskStatus]:
    """Get the global task status database."""
    return task_status_db

def update_task_status(task_id: str, status: TaskStatus):
    """Update task status in the global database."""
    task_status_db[task_id] = status

def get_task_status(task_id: str) -> TaskStatus:
    """Get task status by ID."""
    return task_status_db.get(task_id)

def delete_task_status(task_id: str):
    """Delete task status from database."""
    task_status_db.pop(task_id, None) 