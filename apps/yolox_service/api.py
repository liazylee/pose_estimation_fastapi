from fastapi import APIRouter, HTTPException
from models import (
    StartServiceRequest, ServiceResponse, TaskCompletionRequest,
    ServiceStatus
)
from service_manager import get_service_manager

router = APIRouter()


@router.get("/")
async def root():
    return {
        "service": "YOLOX Detection Service",
        "version": "1.0.0",
        "description": "Microservice for YOLOX object detection with dynamic task_id support",
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
    manager = get_service_manager()
    result = await manager.start_service(
        task_id=request.task_id,
        config_path=request.config_path,
        devices=request.devices,
        log_level=request.log_level,
        max_restarts=request.max_restarts,
        auto_stop_on_completion=request.auto_stop_on_completion
    )
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


@router.post("/services/{task_id}/stop", response_model=ServiceResponse)
async def stop_service(task_id: str):
    manager = get_service_manager()
    result = await manager.stop_service(task_id)
    if result["success"]:
        return ServiceResponse(
            success=True,
            message=result["message"]
        )
    else:
        raise HTTPException(status_code=404, detail=result["message"])


@router.post("/services/{task_id}/complete", response_model=ServiceResponse)
async def complete_task(task_id: str, request: TaskCompletionRequest):
    manager = get_service_manager()
    result = await manager.mark_task_completed(task_id, request.reason)
    if result["success"]:
        return ServiceResponse(
            success=True,
            message=result["message"]
        )
    else:
        raise HTTPException(status_code=404, detail=result["message"])


@router.get("/services/{task_id}/status", response_model=ServiceStatus)
async def get_service_status(task_id: str):
    manager = get_service_manager()
    service_info = manager.get_service_status(task_id)
    if not service_info:
        raise HTTPException(status_code=404, detail=f"YOLOX service with task_id '{task_id}' not found")
    return ServiceStatus(
        task_id=task_id,
        status=service_info["status"],
        started_at=service_info.get("started_at"),
        completed_at=service_info.get("completed_at"),
        error_message=service_info.get("error_message"),
        restart_count=service_info.get("restart_count", 0),
        max_restarts=service_info.get("max_restarts", 30),
        topics={
            "input": f"raw_frames_{task_id}",
            "output": f"yolox_detections_{task_id}",
            "consumer_group": f"yolox_consumers_{task_id}"
        } if service_info["status"] in ["running", "starting"] else None,
        config=service_info.get("config")
    )


@router.get("/services", response_model=list[ServiceStatus])
async def list_all_services():
    manager = get_service_manager()
    services = manager.get_all_services()
    return [
        ServiceStatus(
            task_id=task_id,
            status=service_info["status"],
            started_at=service_info.get("started_at"),
            completed_at=service_info.get("completed_at"),
            error_message=service_info.get("error_message"),
            restart_count=service_info.get("restart_count", 0),
            max_restarts=service_info.get("max_restarts", 30),
            topics={
                "input": f"raw_frames_{task_id}",
                "output": f"yolox_detections_{task_id}",
                "consumer_group": f"yolox_consumers_{task_id}"
            } if service_info["status"] in ["running", "starting"] else None,
            config=service_info.get("config")
        )
        for task_id, service_info in services.items()
    ]


@router.delete("/services")
async def stop_all_services():
    manager = get_service_manager()
    await manager.cleanup_all()
    return {"success": True, "message": "All YOLOX services stopped successfully"}
