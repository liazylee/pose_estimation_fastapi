import traceback
from fastapi import APIRouter, HTTPException

from .models import (
    StartServiceRequest, ServiceResponse, TaskCompletionRequest,
    ServiceStatus
)
from .service_config import ServiceConfig


def create_api_router(service_manager_getter, config: ServiceConfig) -> APIRouter:
    """Create API router for an AI service with common endpoints."""
    
    router = APIRouter()

    @router.get("/")
    async def root():
        return {
            "service": config.service_name,
            "version": config.service_version,
            "description": config.service_description,
            "endpoints": {
                "start": "POST /services/start",
                "stop": "POST /services/{task_id}/stop",
                "complete": "POST /services/{task_id}/complete",
                "status": "GET /services/{task_id}/status",
                "list": "GET /services",
                "stop_all": "DELETE /services",
                "health": "GET /health"
            }
        }

    @router.post("/services/start", response_model=ServiceResponse)
    async def start_service(request: StartServiceRequest):
        manager = service_manager_getter()
        result = await manager.start_service(
            task_id=request.task_id,
            config_path=request.config_path,
            devices=request.devices,
            log_level=request.log_level,
            max_restarts=request.max_restarts,
            auto_stop_on_completion=request.auto_stop_on_completion
        )
        try:
            if result["success"]:
                service_status = manager.get_service_status(request.task_id)
                return ServiceResponse(
                    success=True,
                    message=result["message"],
                    service_status=ServiceStatus(
                        task_id=request.task_id,
                        status=service_status["status"],
                        started_at=service_status["started_at"],
                        restart_count=service_status.get("restart_count", 0),
                        max_restarts=service_status.get("max_restarts", 30),
                        topics=result.get("topics"),
                        config=service_status.get("config")
                    )
                )
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal Server Error: failed to construct ServiceResponse")

    @router.post("/services/{task_id}/stop", response_model=ServiceResponse)
    async def stop_service(task_id: str):
        manager = service_manager_getter()
        result = await manager.stop_service(task_id)
        if result["success"]:
            return ServiceResponse(
                success=True,
                message=result["message"]
            )
        else:
            raise HTTPException(status_code=404, detail=result["message"])

    @router.post("/services/{task_id}/complete", response_model=ServiceResponse)
    async def complete_service(task_id: str, request: TaskCompletionRequest):
        """Mark a service as completed (used by external systems to signal completion)."""
        manager = service_manager_getter()

        # Check if service exists
        service_info = manager.get_service_status(task_id)
        if not service_info:
            raise HTTPException(status_code=404, detail=f"{config.service_name} service with task_id '{task_id}' not found")

        # Stop the service
        result = await manager.stop_service(task_id)

        return ServiceResponse(
            success=True,
            message=f"{config.service_name} service marked as completed for task_id: {task_id}"
        )

    @router.get("/services/{task_id}/status", response_model=ServiceStatus)
    async def get_service_status(task_id: str):
        manager = service_manager_getter()
        service_info = manager.get_service_status(task_id)
        if not service_info:
            raise HTTPException(status_code=404, detail=f"{config.service_name} service with task_id '{task_id}' not found")
        
        return ServiceStatus(
            task_id=task_id,
            status=service_info["status"],
            started_at=service_info.get("started_at"),
            completed_at=service_info.get("completed_at"),
            error_message=service_info.get("error_message"),
            restart_count=service_info.get("restart_count", 0),
            max_restarts=service_info.get("max_restarts", 30),
            topics=config.get_topics_for_task(task_id) if service_info["status"] in ["running", "starting"] else None,
            config=service_info.get("config")
        )

    @router.get("/services", response_model=list[ServiceStatus])
    async def list_all_services():
        manager = service_manager_getter()
        services = manager.get_all_services()
        try:
            return [
                ServiceStatus(
                    task_id=task_id,
                    status=service_info["status"],
                    started_at=service_info.get("started_at"),
                    completed_at=service_info.get("completed_at"),
                    error_message=service_info.get("error_message"),
                    restart_count=service_info.get("restart_count", 0),
                    max_restarts=service_info.get("max_restarts", 30),
                    topics=config.get_topics_for_task(task_id) if service_info["status"] in ["running", "starting"] else None,
                    config=service_info.get("config")
                )
                for task_id, service_info in services.items()
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal Server Error: failed to construct ServiceStatus")

    @router.delete("/services")
    async def stop_all_services():
        manager = service_manager_getter()
        await manager.cleanup_all()
        return {"success": True, "message": f"All {config.service_name} services stopped successfully"}

    return router 