import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from .service_config import ServiceConfig

logger = logging.getLogger(__name__)


class BaseServiceManager:
    """Base class for managing multiple AI service instances."""

    def __init__(self, config: ServiceConfig):
        self.config = config
        self.services: Dict[str, Dict[str, Any]] = {}  # task_id -> service_info
        self.tasks: Dict[str, asyncio.Task] = {}  # task_id -> asyncio task
        self._lock = asyncio.Lock()
        self.start_time = time.time()
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
                            service_info.get("restart_count", 0) >= service_info.get("max_restarts", 3)):
                        await self._mark_service_failed(task_id, "Maximum restart attempts exceeded")

                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in {self.config.service_name} service monitoring: {e}")
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
                logger.error(f"{self.config.service_name} service {task_id} marked as failed: {reason}")

        # Stop the service
        await self.stop_service(task_id)

    async def mark_task_completed(self, task_id: str, reason: str = "Task completed successfully") -> Dict[str, Any]:
        """Mark a task as completed and optionally stop the service."""
        async with self._lock:
            if task_id not in self.services:
                return {
                    "success": False,
                    "message": f"No {self.config.service_name} service found with task_id: {task_id}"
                }

            service_info = self.services[task_id]
            auto_stop = service_info.get("config", {}).get("auto_stop_on_completion", True)

            # Update service status
            self.services[task_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "error_message": None
            })

            logger.info(f"{self.config.service_name} task {task_id} marked as completed: {reason}")

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

    async def start_service(self, task_id: str, config_path: str = None,
                            devices: Optional[List[str]] = None, log_level: Optional[str] = None,
                            max_restarts: int = 30, auto_stop_on_completion: bool = True) -> Dict[str, Any]:
        """Start an AI service with the given task_id."""
        
        if config_path is None:
            config_path = self.config.default_config_path

        async with self._lock:
            if task_id in self.services:
                if self.services[task_id]["status"] in ["running", "starting"]:
                    return {
                        "success": False,
                        "message": f"{self.config.service_name} service with task_id '{task_id}' is already running"
                    }

            try:
                # Create service instance using factory
                service = self.config.service_factory(config_path=config_path, task_id=task_id)

                # Override config with provided parameters
                if devices:
                    service.config.setdefault(self.config.service_name.lower(), {})['devices'] = devices
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

                logger.info(f"Started {self.config.service_name} service for task_id: {task_id} (max_restarts: {max_restarts})")

                return {
                    "success": True,
                    "message": f"{self.config.service_name} service started successfully for task_id: {task_id}",
                    "topics": self.config.get_topics_for_task(task_id)
                }

            except Exception as e:
                error_msg = f"Failed to start {self.config.service_name} service for task_id '{task_id}': {str(e)}"
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

    async def _run_service(self, task_id: str, service):
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
                async with self._lock:
                    if task_id in self.services:
                        self.services[task_id].update({
                            "status": "completed",
                            "completed_at": datetime.now().isoformat()
                        })
                break

            except asyncio.CancelledError:
                logger.info(f"{self.config.service_name} service for task_id '{task_id}' was cancelled")
                async with self._lock:
                    if task_id in self.services:
                        self.services[task_id]["status"] = "stopped"
                break

            except Exception as e:
                error_msg = f"{self.config.service_name} service error for task_id '{task_id}': {str(e)}"
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
                            logger.error(f"{self.config.service_name} service {task_id} failed after {max_restarts} restart attempts")
                            break
                        else:
                            logger.warning(f"Restarting {self.config.service_name} service {task_id} (attempt {restart_count}/{max_restarts})")
                            # Wait before restarting
                            await asyncio.sleep(min(restart_count * 2, 60))  # Exponential backoff, max 60s

        # Cleanup task reference
        async with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop an AI service."""

        async with self._lock:
            if task_id not in self.services:
                return {
                    "success": False,
                    "message": f"No {self.config.service_name} service found with task_id: {task_id}"
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
                    logger.warning(f"Timeout waiting for {self.config.service_name} service {task_id} to stop")

            # Update service status
            async with self._lock:
                if task_id in self.services:
                    if self.services[task_id]["status"] not in ["completed", "failed"]:
                        self.services[task_id]["status"] = "stopped"
                        self.services[task_id]["completed_at"] = datetime.now().isoformat()

            logger.info(f"Stopped {self.config.service_name} service for task_id: {task_id}")

            return {
                "success": True,
                "message": f"{self.config.service_name} service stopped successfully for task_id: {task_id}"
            }

        except Exception as e:
            error_msg = f"Failed to stop {self.config.service_name} service for task_id '{task_id}': {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }

    def get_service_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific AI service."""
        return self.services.get(task_id)

    def get_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all AI services."""
        return self.services.copy()

    async def cleanup_all(self):
        """Stop and cleanup all services."""
        logger.info(f"Stopping all {self.config.service_name} services...")

        # Stop monitoring
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None

        # Get list of active task IDs
        task_ids = list(self.tasks.keys())

        # Cancel all tasks
        for task_id in task_ids:
            try:
                await self.stop_service(task_id)
            except Exception as e:
                logger.error(f"Error stopping {self.config.service_name} service {task_id}: {e}")

        # Clear all data
        async with self._lock:
            self.services.clear()
            self.tasks.clear()

        logger.info(f"All {self.config.service_name} services stopped")

    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary of all services."""
        now = datetime.now().isoformat()
        uptime = time.time() - self.start_time

        running_count = 0
        error_count = 0
        stopped_count = 0
        completed_count = 0
        failed_count = 0
        service_status = {}

        for task_id, service_info in self.services.items():
            status = service_info["status"]
            service_status[task_id] = status

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

        total_services = len(self.services)
        healthy = error_count == 0 and failed_count == 0

        return {
            "healthy": healthy,
            "total_services": total_services,
            "running_services": running_count,
            "error_services": error_count,
            "stopped_services": stopped_count,
            "completed_services": completed_count,
            "failed_services": failed_count,
            "services": service_status,
            "uptime_seconds": uptime,
            "last_check": now
        } 