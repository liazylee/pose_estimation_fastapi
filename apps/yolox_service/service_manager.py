# service_manager.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from service import YOLOXService  # 你的检测核心

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages multiple YOLOX service instances."""

    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self.monitoring_task = None

    def _start_monitoring(self):
        """Start background monitoring for auto-completion and restart limits."""
        if self.monitoring_task is None:
            self.monitoring_task = asyncio.create_task(self._monitor_services())

    async def _monitor_services(self):
        """Background task to monitor service health and completion."""
        while True:
            try:
                async with self._lock:
                    services_to_check = list(self.services.keys())

                for task_id in services_to_check:
                    service_info = self.services.get(task_id)
                    if not service_info:
                        continue

                    # Check if service should be auto-stopped due to restart limit
                    if (service_info["status"] == "error" and
                            service_info.get("restart_count", 0) >= service_info.get("max_restarts", 30)):
                        await self._mark_service_failed(task_id, "Maximum restart attempts exceeded")

                    # Here you could add other monitoring logic like:
                    # - Check for idle timeout
                    # - Monitor processing queue
                    # - Health checks, etc.

                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in service monitoring: {e}")
                await asyncio.sleep(30)  # Wait longer on error

    async def _mark_service_failed(self, task_id: str, reason: str):
        """Mark a service as failed and stop it."""
        async with self._lock:
            if task_id in self.services:
                self.services[task_id].update({
                    "status": "failed",
                    "completed_at": datetime.now().isoformat(),
                    "error_message": reason
                })
                logger.error(f"Service {task_id} marked as failed: {reason}")

        # Stop the service
        await self.stop_service(task_id)

    async def mark_task_completed(self, task_id: str, reason: str = "Task completed successfully") -> Dict[str, Any]:
        """Mark a task as completed and optionally stop the service."""
        async with self._lock:
            if task_id not in self.services:
                return {
                    "success": False,
                    "message": f"No YOLOX service found with task_id: {task_id}"
                }

            service_info = self.services[task_id]
            auto_stop = service_info.get("config", {}).get("auto_stop_on_completion", True)

            # Update service status
            self.services[task_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "error_message": None
            })

            logger.info(f"Task {task_id} marked as completed: {reason}")

        # Auto-stop if configured
        if auto_stop:
            await self.stop_service(task_id)
            message = f"Task {task_id} completed and service stopped automatically"
        else:
            message = f"Task {task_id} marked as completed"

        return {
            "success": True,
            "message": message
        }

    async def start_service(self, task_id: str, config_path: str = "dev_pose_estimation_config.yaml",
                            devices: Optional[List[str]] = None, log_level: Optional[str] = None,
                            max_restarts: int = 30, auto_stop_on_completion: bool = True) -> Dict[str, Any]:
        """Start a YOLOX service with the given task_id."""

        async with self._lock:
            if task_id in self.services:
                if self.services[task_id]["status"] in ["running", "starting"]:
                    return {
                        "success": False,
                        "message": f"YOLOX service with task_id '{task_id}' is already running"
                    }

            try:
                # Create service instance
                service = YOLOXService(config_path=config_path, task_id=task_id)

                # Override config with provided parameters
                if devices:
                    service.config.setdefault('yolox', {})['devices'] = devices
                if log_level:
                    service.config.setdefault('global', {})['log_level'] = log_level

                # Store service info
                self.services[task_id] = {
                    "service": service,
                    "status": "starting",
                    "started_at": datetime.now().isoformat(),
                    "completed_at": None,
                    "error_message": None,
                    "restart_count": 0,
                    "max_restarts": max_restarts,
                    "config": {
                        "config_path": config_path,
                        "devices": devices,
                        "log_level": log_level,
                        "max_restarts": max_restarts,
                        "auto_stop_on_completion": auto_stop_on_completion
                    }
                }

                # Start service as background task
                task = asyncio.create_task(self._run_service(task_id, service))
                self.tasks[task_id] = task

                logger.info(f"Started YOLOX service for task_id: {task_id} (max_restarts: {max_restarts})")

                return {
                    "success": True,
                    "message": f"YOLOX service started successfully for task_id: {task_id}",
                    "topics": {
                        "input": f"raw_frames_{task_id}",
                        "output": f"yolox_detections_{task_id}",
                        "consumer_group": f"yolox_consumers_{task_id}"
                    }
                }

            except Exception as e:
                error_msg = f"Failed to start YOLOX service for task_id '{task_id}': {str(e)}"
                logger.error(error_msg)

                # Update service status
                if task_id in self.services:
                    self.services[task_id].update({
                        "status": "error",
                        "error_message": error_msg
                    })

                return {
                    "success": False,
                    "message": error_msg
                }

    async def _run_service(self, task_id: str, service: YOLOXService):
        """Run the service in background with restart logic."""
        while True:
            try:
                # Update status to running
                async with self._lock:
                    if task_id in self.services:
                        service_info = self.services[task_id]
                        if service_info["status"] in ["completed", "failed", "stopped"]:
                            break  # Don't restart if manually stopped or completed

                        self.services[task_id]["status"] = "running"

                # Start the service
                await service.start_service()

                # If we reach here, service completed normally
                break

            except asyncio.CancelledError:
                logger.info(f"YOLOX service for task_id '{task_id}' was cancelled")
                async with self._lock:
                    if task_id in self.services:
                        self.services[task_id]["status"] = "stopped"
                break

            except Exception as e:
                error_msg = f"YOLOX service error for task_id '{task_id}': {str(e)}"
                logger.error(error_msg)

                async with self._lock:
                    if task_id in self.services:
                        service_info = self.services[task_id]
                        restart_count = service_info.get("restart_count", 0) + 1
                        max_restarts = service_info.get("max_restarts", 30)

                        self.services[task_id].update({
                            "status": "error",
                            "error_message": error_msg,
                            "restart_count": restart_count
                        })

                        # Check if we should restart
                        if restart_count >= max_restarts:
                            self.services[task_id].update({
                                "status": "failed",
                                "completed_at": datetime.now().isoformat(),
                                "error_message": f"Service failed after {max_restarts} restart attempts: {error_msg}"
                            })
                            logger.error(f"Service {task_id} failed after {max_restarts} restart attempts")
                            break
                        else:
                            logger.warning(f"Restarting service {task_id} (attempt {restart_count}/{max_restarts})")
                            # Wait before restarting
                            await asyncio.sleep(min(restart_count * 2, 60))  # Exponential backoff, max 60s

        # Cleanup task reference
        async with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop a YOLOX service."""

        async with self._lock:
            if task_id not in self.services:
                return {
                    "success": False,
                    "message": f"No YOLOX service found with task_id: {task_id}"
                }

        try:
            # Cancel the task
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.cancel()

                # Wait for task to complete
                try:
                    await asyncio.wait_for(task, timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for YOLOX service {task_id} to stop")

            # Update service status
            async with self._lock:
                if task_id in self.services:
                    if self.services[task_id]["status"] not in ["completed", "failed"]:
                        self.services[task_id]["status"] = "stopped"
                        self.services[task_id]["completed_at"] = datetime.now().isoformat()

            logger.info(f"Stopped YOLOX service for task_id: {task_id}")

            return {
                "success": True,
                "message": f"YOLOX service stopped successfully for task_id: {task_id}"
            }

        except Exception as e:
            error_msg = f"Failed to stop YOLOX service for task_id '{task_id}': {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }

    def get_service_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific YOLOX service."""
        return self.services.get(task_id)

    def get_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all YOLOX services."""
        return self.services.copy()

    async def cleanup_all(self):
        """Stop all running YOLOX services."""
        # Stop monitoring
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None

        # Stop all services
        tasks_to_stop = []
        async with self._lock:
            for task_id in list(self.services.keys()):
                if self.services[task_id]["status"] in ["running", "starting"]:
                    tasks_to_stop.append(task_id)

        for task_id in tasks_to_stop:
            await self.stop_service(task_id)

    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary of all YOLOX services."""
        running_count = 0
        error_count = 0
        stopped_count = 0
        completed_count = 0
        failed_count = 0

        for service_info in self.services.values():
            status = service_info["status"]
            if status == "running":
                running_count += 1
            elif status == "error":
                error_count += 1
            elif status == "stopped":
                stopped_count += 1
            elif status == "completed":
                completed_count += 1
            elif status == "failed":
                failed_count += 1

        return {
            "total_services": len(self.services),
            "running": running_count,
            "stopped": stopped_count,
            "errors": error_count,
            "completed": completed_count,
            "failed": failed_count,
            "healthy": error_count == 0 and failed_count == 0
        }


# 单例模式
_service_manager = None


def get_service_manager():
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
