"""
Service Manager for Annotation Service.
Manages multiple annotation service instances and their lifecycle.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

from service import AnnotationService

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages multiple annotation service instances."""

    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}  # task_id -> service_info
        self.tasks: Dict[str, asyncio.Task] = {}  # task_id -> asyncio task
        self._lock = asyncio.Lock()
        self.start_time = time.time()

    async def start_service(self, task_id: str, config_path: str = "dev_pose_estimation_config.yaml",
                            log_level: Optional[str] = None, max_restarts: int = 30,
                            auto_stop_on_completion: bool = True) -> Dict[str, Any]:
        """Start an annotation service with the given task_id."""

        async with self._lock:
            if task_id in self.services:
                if self.services[task_id]["status"] in ["running", "starting"]:
                    return {
                        "success": False,
                        "message": f"Annotation service with task_id '{task_id}' is already running"
                    }

            try:
                # Create service instance
                service = AnnotationService(config_path=config_path, task_id=task_id)

                # Override config with provided parameters
                if log_level:
                    # We can add log level configuration if needed
                    pass

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
                        "log_level": log_level,
                        "max_restarts": max_restarts,
                        "auto_stop_on_completion": auto_stop_on_completion
                    }
                }

                # Start service as background task
                task = asyncio.create_task(self._run_service(task_id, service))
                self.tasks[task_id] = task

                logger.info(f"Started annotation service for task_id: {task_id} (max_restarts: {max_restarts})")

                return {
                    "success": True,
                    "message": f"Annotation service started successfully for task_id: {task_id}",
                    "outputs": {
                        "rtsp_stream": f"rtsp://localhost:8554/outstream_{task_id}",
                        "video_file": f"output_videos/{task_id}/annotated_{task_id}_[timestamp].mp4",
                        "debug_frames": f"debug_frames/{task_id}/"
                    },
                    "inputs": {
                        "raw_frames": f"raw_frames_{task_id}",
                        "detections": f"yolox_detections_{task_id}",
                        "poses": f"rtmpose_results_{task_id}"
                    },
                    "consumer_groups": [
                        f"annotation_raw_{task_id}",
                        f"annotation_track_{task_id}",
                        f"annotation_pose_{task_id}"
                    ]
                }

            except Exception as e:
                error_msg = f"Failed to start annotation service for task_id '{task_id}': {str(e)}"
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

    async def _run_service(self, task_id: str, service: AnnotationService):
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
                logger.info(f"Annotation service for task_id '{task_id}' was cancelled")
                async with self._lock:
                    if task_id in self.services:
                        self.services[task_id]["status"] = "stopped"
                break

            except Exception as e:
                error_msg = f"Annotation service error for task_id '{task_id}': {str(e)}"
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
                            logger.warning(
                                f"Restarting annotation service {task_id} (attempt {restart_count}/{max_restarts})")
                            # Wait before restarting
                            await asyncio.sleep(min(restart_count * 2, 60))  # Exponential backoff, max 60s

        # Cleanup task reference
        async with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop an annotation service."""

        async with self._lock:
            if task_id not in self.services:
                return {
                    "success": False,
                    "message": f"No annotation service found with task_id: {task_id}"
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
                    logger.warning(f"Timeout waiting for annotation service {task_id} to stop")

            # Update service status
            async with self._lock:
                if task_id in self.services:
                    if self.services[task_id]["status"] not in ["completed", "failed"]:
                        self.services[task_id]["status"] = "stopped"
                        self.services[task_id]["completed_at"] = datetime.now().isoformat()

            logger.info(f"Stopped annotation service for task_id: {task_id}")

            return {
                "success": True,
                "message": f"Annotation service stopped successfully for task_id: {task_id}"
            }

        except Exception as e:
            error_msg = f"Failed to stop annotation service for task_id '{task_id}': {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }

    def get_service_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific annotation service."""
        return self.services.get(task_id)

    def get_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all annotation services."""
        return self.services.copy()

    async def cleanup_all(self):
        """Stop and cleanup all services."""
        logger.info("Stopping all annotation services...")

        # Get list of active task IDs
        task_ids = list(self.tasks.keys())

        # Cancel all tasks
        for task_id in task_ids:
            try:
                await self.stop_service(task_id)
            except Exception as e:
                logger.error(f"Error stopping service {task_id}: {e}")

        # Clear all data
        async with self._lock:
            self.services.clear()
            self.tasks.clear()

        logger.info("All annotation services stopped")

    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary of all services."""
        now = datetime.now().isoformat()
        uptime = time.time() - self.start_time

        running_count = 0
        error_count = 0
        service_status = {}

        for task_id, service_info in self.services.items():
            status = service_info["status"]
            service_status[task_id] = status

            if status == "running":
                running_count += 1
            elif status in ["error", "failed"]:
                error_count += 1

        total_services = len(self.services)
        healthy = error_count == 0 and (total_services == 0 or running_count > 0)

        return {
            "healthy": healthy,
            "total_services": total_services,
            "running_services": running_count,
            "error_services": error_count,
            "services": service_status,
            "uptime_seconds": uptime,
            "last_check": now
        }

    def _start_monitoring(self):
        """Start background monitoring (placeholder for future use)."""
        logger.info("Annotation service monitoring started")


# Global service manager instance
_service_manager = None


def get_service_manager() -> ServiceManager:
    """Get the global service manager instance."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
