"""
Pydantic schemas for FastAPI endpoints.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class TaskResponse(BaseModel):
    """Response model for task creation."""
    task_id: str
    message: str
    stream_url: str


class TaskStatus(BaseModel):
    """Task status information."""
    task_id: str
    status: str  # initializing, processing, completed, failed
    progress: int  # 0-100
    created_at: datetime
    updated_at: Optional[datetime] = None
    input_file: str
    output_file: Optional[str] = None
    error: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AIPipelineStartRequest(BaseModel):
    """Request model for starting AI pipeline."""
    task_id: str
    config: Optional[Dict[str, Any]] = None