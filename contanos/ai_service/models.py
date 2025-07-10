from typing import Optional, Dict, Any, List

from pydantic import BaseModel


class StartServiceRequest(BaseModel):
    """Request model for starting AI service."""
    task_id: str
    config_path: Optional[str] = "dev_pose_estimation_config.yaml"
    devices: Optional[List[str]] = None
    log_level: Optional[str] = None
    max_restarts: Optional[int] = 30
    auto_stop_on_completion: Optional[bool] = True


class ServiceResponse(BaseModel):
    """Response model for service operations."""
    success: bool
    message: str
    service_status: Optional["ServiceStatus"] = None


class TaskCompletionRequest(BaseModel):
    """Request model for marking task as completed."""
    reason: Optional[str] = "Task completed successfully"


class ServiceStatus(BaseModel):
    """Model for service status information."""
    task_id: str
    status: str  # running, stopped, error, completed, failed, starting
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    restart_count: Optional[int] = 0
    max_restarts: Optional[int] = 30
    topics: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


class HealthSummary(BaseModel):
    """Model for health check summary."""
    healthy: bool
    total_services: int
    running_services: int
    error_services: int
    stopped_services: Optional[int] = 0
    completed_services: Optional[int] = 0
    failed_services: Optional[int] = 0
    services: Optional[Dict[str, str]] = None
    uptime_seconds: Optional[float] = None
    last_check: Optional[str] = None


# Forward reference resolution
ServiceResponse.model_rebuild() 