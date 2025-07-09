from typing import Optional, Dict, Any, Union, List

from pydantic import BaseModel


class StartServiceRequest(BaseModel):
    """Request model for starting annotation service."""
    task_id: str
    config_path: Optional[str] = "dev_pose_estimation_config.yaml"
    log_level: Optional[str] = None
    max_restarts: Optional[int] = 30
    auto_stop_on_completion: Optional[bool] = True


class ServiceStatus(BaseModel):
    """Response model for service status."""
    task_id: str
    status: str  # "starting", "running", "stopped", "error", "completed", "failed"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    restart_count: int = 0
    max_restarts: int = 30
    # except Optional[Dict[str, str or list[str]]]
    topics: Optional[Dict[str, Union[str, List[str]]]] = None
    config: Optional[Dict[str, Any]] = None


class ServiceResponse(BaseModel):
    """Generic response model for service operations."""
    success: bool
    message: str
    service_status: Optional[ServiceStatus] = None


class TaskCompletionRequest(BaseModel):
    """Request model for task completion notification."""
    task_id: str
    completed_at: Optional[str] = None
    final_frame_count: Optional[int] = None


class HealthSummary(BaseModel):
    """Response model for health check."""
    healthy: bool
    total_services: int
    running_services: int
    error_services: int
    services: Dict[str, str]  # task_id -> status
    uptime_seconds: float
    last_check: str
