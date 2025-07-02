from typing import Optional, Dict, Any, List

from pydantic import BaseModel


class StartServiceRequest(BaseModel):
    task_id: str
    config_path: Optional[str] = "dev_pose_estimation_config.yaml"
    devices: Optional[List[str]] = None
    log_level: Optional[str] = None
    max_restarts: Optional[int] = 30
    auto_stop_on_completion: Optional[bool] = True


class ServiceStatus(BaseModel):
    task_id: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    restart_count: Optional[int] = 0
    max_restarts: Optional[int] = 30
    topics: Optional[Dict[str, str]] = None
    config: Optional[Dict[str, Any]] = None


class TaskCompletionRequest(BaseModel):
    task_id: str
    reason: Optional[str] = "Task completed successfully"


class ServiceResponse(BaseModel):
    success: bool
    message: str
    service_status: Optional[ServiceStatus] = None


class HealthSummary(BaseModel):
    total_services: int
    running: int
    stopped: int
    errors: int
    completed: int
    failed: int
    healthy: bool
