"""
AI Service Client for communicating with AI microservices.
Handles HTTP requests to various AI services (YOLOX, RTMPose, ByteTrack, etc.).
"""
import logging
from typing import Dict, Any, Optional, List

import httpx

logger = logging.getLogger(__name__)


class AIServiceClient:
    """HTTP client for AI microservices."""

    def __init__(self, service_urls: Dict[str, str]):
        """
        Initialize AI service client.
        
        Args:
            service_urls: Dictionary mapping service names to their base URLs
                         e.g., {"yolox": "http://localhost:8001", "rtmpose": "http://localhost:8002"}
        """
        self.service_urls = service_urls
        self.timeout = 30.0

    async def _make_request(self, method: str, service: str, endpoint: str,
                            json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to a service."""

        if service not in self.service_urls:
            raise ValueError(f"Unknown service '{service}'. Available services: {list(self.service_urls.keys())}")

        base_url = self.service_urls[service]
        url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.error(f"Timeout calling {service} service at {url}")
            raise Exception(f"Timeout calling {service} service")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {service} service: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP error calling {service} service: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error calling {service} service: {str(e)}")
            raise Exception(f"Error calling {service} service: {str(e)}")


class YOLOXServiceClient(AIServiceClient):
    """Client specifically for YOLOX detection service."""

    def __init__(self, yolox_url: str = "http://localhost:8001"):
        """Initialize YOLOX service client."""
        super().__init__({"yolox": yolox_url})

    async def start_service(self, task_id: str, config_path: Optional[str] = None,
                            devices: Optional[List[str]] = None, log_level: Optional[str] = None) -> Dict[str, Any]:
        """Start a YOLOX detection service."""

        request_data = {"task_id": task_id}
        if config_path:
            request_data["config_path"] = config_path
        if devices:
            request_data["devices"] = devices
        if log_level:
            request_data["log_level"] = log_level

        return await self._make_request("POST", "yolox", "services/start", json_data=request_data)

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop a YOLOX detection service."""
        return await self._make_request("POST", "yolox", f"services/{task_id}/stop")

    async def get_service_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a YOLOX service."""
        return await self._make_request("GET", "yolox", f"services/{task_id}/status")

    async def list_services(self) -> List[Dict[str, Any]]:
        """List all YOLOX services."""
        return await self._make_request("GET", "yolox", "services")

    async def stop_all_services(self) -> Dict[str, Any]:
        """Stop all YOLOX services."""
        return await self._make_request("DELETE", "yolox", "services")

    async def get_health(self) -> Dict[str, Any]:
        """Get YOLOX service health status."""
        return await self._make_request("GET", "yolox", "health")

    async def ping(self) -> bool:
        """Ping YOLOX service to check if it's available."""
        try:
            await self._make_request("GET", "yolox", "")
            return True
        except Exception:
            return False


class RTMPoseServiceClient(AIServiceClient):
    """Client for RTMPose pose estimation service."""

    def __init__(self, rtmpose_url: str = "http://localhost:8002"):
        super().__init__({"rtmpose": rtmpose_url})

    async def start_service(self, task_id: str, config_path: Optional[str] = None,
                            devices: Optional[List[str]] = None, log_level: Optional[str] = None) -> Dict[str, Any]:
        """Start a RTMPose service."""

        request_data = {"task_id": task_id}
        if config_path:
            request_data["config_path"] = config_path
        if devices:
            request_data["devices"] = devices
        if log_level:
            request_data["log_level"] = log_level

        return await self._make_request("POST", "rtmpose", "services/start", json_data=request_data)

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop a RTMPose service."""
        return await self._make_request("POST", "rtmpose", f"services/{task_id}/stop")

    async def get_service_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a RTMPose service."""
        return await self._make_request("GET", "rtmpose", f"services/{task_id}/status")

    async def list_services(self) -> List[Dict[str, Any]]:
        """List all RTMPose services."""
        return await self._make_request("GET", "rtmpose", "services")

    async def stop_all_services(self) -> Dict[str, Any]:
        """Stop all RTMPose services."""
        return await self._make_request("DELETE", "rtmpose", "services")

    async def get_health(self) -> Dict[str, Any]:
        """Get RTMPose service health status."""
        return await self._make_request("GET", "rtmpose", "health")

    async def ping(self) -> bool:
        """Ping RTMPose service to check if it's available."""
        try:
            await self._make_request("GET", "rtmpose", "")
            return True
        except Exception:
            return False


class ByteTrackServiceClient(AIServiceClient):
    """Client for ByteTrack service (placeholder for future implementation)."""

    def __init__(self, bytetrack_url: str = "http://localhost:8003"):
        super().__init__({"bytetrack": bytetrack_url})

    async def start_service(self, task_id: str) -> Dict[str, Any]:
        """Start ByteTrack service - placeholder."""
        # TODO: Implement when ByteTrack microservice is ready
        raise NotImplementedError("ByteTrack microservice not implemented yet")


class AnnotationServiceClient(AIServiceClient):
    """Client for Annotation service."""

    def __init__(self, annotation_url: str = "http://localhost:8004"):
        super().__init__({"annotation": annotation_url})

    async def start_service(self, task_id: str, config_path: Optional[str] = None,
                            log_level: Optional[str] = None, max_restarts: Optional[int] = None) -> Dict[str, Any]:
        """Start an annotation service."""

        request_data = {"task_id": task_id}
        if config_path:
            request_data["config_path"] = config_path
        if log_level:
            request_data["log_level"] = log_level
        if max_restarts:
            request_data["max_restarts"] = max_restarts

        return await self._make_request("POST", "annotation", "services/start", json_data=request_data)

    async def stop_service(self, task_id: str) -> Dict[str, Any]:
        """Stop an annotation service."""
        return await self._make_request("POST", "annotation", f"services/{task_id}/stop")

    async def get_service_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of an annotation service."""
        return await self._make_request("GET", "annotation", f"services/{task_id}/status")

    async def list_services(self) -> List[Dict[str, Any]]:
        """List all annotation services."""
        return await self._make_request("GET", "annotation", "services")

    async def stop_all_services(self) -> Dict[str, Any]:
        """Stop all annotation services."""
        return await self._make_request("DELETE", "annotation", "services")

    async def get_health(self) -> Dict[str, Any]:
        """Get annotation service health status."""
        return await self._make_request("GET", "annotation", "health")

    async def ping(self) -> bool:
        """Ping annotation service to check if it's available."""
        try:
            await self._make_request("GET", "annotation", "")
            return True
        except Exception:
            return False


class AIServiceOrchestrator:
    """Orchestrates multiple AI services for a complete video processing pipeline."""

    def __init__(self, service_config: Optional[Dict[str, str]] = None):
        """
        Initialize AI service orchestrator.
        
        Args:
            service_config: Dictionary mapping service names to URLs
        """
        if service_config is None:
            service_config = {
                "yolox": "http://localhost:8001",
                "rtmpose": "http://localhost:8002",
                "bytetrack": "http://localhost:8003",
                "annotation": "http://localhost:8004"
            }

        self.yolox_client = YOLOXServiceClient(service_config["yolox"])
        self.rtmpose_client = RTMPoseServiceClient(service_config["rtmpose"])
        self.bytetrack_client = ByteTrackServiceClient(service_config["bytetrack"])
        self.annotation_client = AnnotationServiceClient(service_config["annotation"])

    async def start_pipeline(self, task_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start the complete AI processing pipeline for a task.
        
        Args:
            task_id: Unique task identifier
            config: Configuration options for services
            
        Returns:
            Dictionary with results from starting each service
        """
        results = {
            "task_id": task_id,
            "services": {},
            "success": True,
            "errors": []
        }

        # Start YOLOX service first
        try:
            logger.info(f"Starting YOLOX service for task {task_id}")
            yolox_result = await self.yolox_client.start_service(
                task_id=task_id,
                config_path=config.get("yolox_config") if config else None,
                devices=config.get("yolox_devices") if config else None,
                log_level=config.get("log_level") if config else None
            )
            results["services"]["yolox"] = yolox_result
            logger.info(f"YOLOX service started successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to start YOLOX service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["yolox"] = {"success": False, "error": error_msg}
            results["success"] = False

        # Start RTMPose service
        try:
            logger.info(f"Starting RTMPose service for task {task_id}")
            rtmpose_result = await self.rtmpose_client.start_service(
                task_id=task_id,
                config_path=config.get("rtmpose_config") if config else None,
                devices=config.get("rtmpose_devices") if config else None,
                log_level=config.get("log_level") if config else None
            )
            results["services"]["rtmpose"] = rtmpose_result
            logger.info(f"RTMPose service started successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to start RTMPose service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["rtmpose"] = {"success": False, "error": error_msg}
            # Don't set overall success=False for RTMPose service failure

        # TODO: Start ByteTrack service when ready

        # Start Annotation service (now implemented)
        try:
            logger.info(f"Starting Annotation service for task {task_id}")
            annotation_result = await self.annotation_client.start_service(
                task_id=task_id,
                config_path=config.get("annotation_config") if config else None,
                log_level=config.get("log_level") if config else None,
                max_restarts=config.get("max_restarts") if config else None
            )
            results["services"]["annotation"] = annotation_result
            logger.info(f"Annotation service started successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to start Annotation service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["annotation"] = {"success": False, "error": error_msg}
            # Don't set success=False for annotation service failure for now
        return results

    async def stop_pipeline(self, task_id: str) -> Dict[str, Any]:
        """
        Stop all AI services for a task.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Dictionary with results from stopping each service
        """
        results = {
            "task_id": task_id,
            "services": {},
            "success": True,
            "errors": []
        }

        # Stop YOLOX service
        try:
            logger.info(f"Stopping YOLOX service for task {task_id}")
            yolox_result = await self.yolox_client.stop_service(task_id)
            results["services"]["yolox"] = yolox_result
            logger.info(f"YOLOX service stopped successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to stop YOLOX service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["yolox"] = {"success": False, "error": error_msg}
            results["success"] = False

        # Stop RTMPose service
        try:
            logger.info(f"Stopping RTMPose service for task {task_id}")
            rtmpose_result = await self.rtmpose_client.stop_service(task_id)
            results["services"]["rtmpose"] = rtmpose_result
            logger.info(f"RTMPose service stopped successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to stop RTMPose service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["rtmpose"] = {"success": False, "error": error_msg}
            # Don't set overall success=False for RTMPose service failure

        # TODO: Stop ByteTrack service when ready

        # Stop Annotation service (now implemented)
        try:
            logger.info(f"Stopping Annotation service for task {task_id}")
            annotation_result = await self.annotation_client.stop_service(task_id)
            results["services"]["annotation"] = annotation_result
            logger.info(f"Annotation service stopped successfully for task {task_id}")

        except Exception as e:
            error_msg = f"Failed to stop Annotation service: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["services"]["annotation"] = {"success": False, "error": error_msg}
            # Don't set success=False for annotation service failure for now

        # TODO: Stop RTMPose and ByteTrack services when ready

        return results

    async def get_pipeline_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of all services in the pipeline for a task."""

        status = {
            "task_id": task_id,
            "services": {},
            "overall_status": "unknown"
        }

        # Get YOLOX status
        try:
            yolox_status = await self.yolox_client.get_service_status(task_id)
            status["services"]["yolox"] = yolox_status
        except Exception as e:
            status["services"]["yolox"] = {"status": "error", "error": str(e)}

        # Get RTMPose status
        try:
            rtmpose_status = await self.rtmpose_client.get_service_status(task_id)
            status["services"]["rtmpose"] = rtmpose_status
        except Exception as e:
            status["services"]["rtmpose"] = {"status": "error", "error": str(e)}

        # TODO: Get ByteTrack status when ready

        # Get Annotation status (now implemented)
        try:
            annotation_status = await self.annotation_client.get_service_status(task_id)
            status["services"]["annotation"] = annotation_status
        except Exception as e:
            status["services"]["annotation"] = {"status": "error", "error": str(e)}

        # Determine overall status
        yolox_service_status = status["services"].get("yolox", {}).get("status", "unknown")
        if yolox_service_status == "running":
            status["overall_status"] = "running"
        elif yolox_service_status == "error":
            status["overall_status"] = "error"
        elif yolox_service_status == "stopped":
            status["overall_status"] = "stopped"
        else:
            status["overall_status"] = "starting"

        return status

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all AI services."""

        health = {
            "services": {},
            "overall_healthy": True
        }

        # Check YOLOX health
        try:
            yolox_health = await self.yolox_client.get_health()
            health["services"]["yolox"] = {
                "healthy": yolox_health.get("healthy", False),
                "details": yolox_health
            }
        except Exception as e:
            health["services"]["yolox"] = {
                "healthy": False,
                "error": str(e)
            }
            health["overall_healthy"] = False

        # Check RTMPose health
        try:
            rtmpose_health = await self.rtmpose_client.get_health()
            health["services"]["rtmpose"] = {
                "healthy": rtmpose_health.get("healthy", False),
                "details": rtmpose_health
            }
        except Exception as e:
            health["services"]["rtmpose"] = {
                "healthy": False,
                "error": str(e)
            }
            health["overall_healthy"] = False

        # TODO: Check ByteTrack health when ready
        health["services"]["bytetrack"] = {"healthy": False, "status": "not_implemented"}

        # Check Annotation health (now implemented)
        try:
            annotation_health = await self.annotation_client.get_health()
            health["services"]["annotation"] = {
                "healthy": annotation_health.get("healthy", False),
                "details": annotation_health
            }
        except Exception as e:
            health["services"]["annotation"] = {
                "healthy": False,
                "error": str(e)
            }
            health["overall_healthy"] = False

        # TODO: Check health of RTMPose and ByteTrack services when they're ready
        health["services"]["rtmpose"] = {"healthy": False, "status": "not_implemented"}
        health["services"]["bytetrack"] = {"healthy": False, "status": "not_implemented"}

        return health

    async def shutdown(self):
        """Shutdown all AI services gracefully."""
        try:
            await self.yolox_client.stop_all_services()
            await self.rtmpose_client.stop_all_services()
            await self.annotation_client.stop_all_services()

        except Exception as e:
            logger.error(f"Error during AI service shutdown: {str(e)}")
            raise Exception(f"Failed to shutdown AI services: {str(e)}") from e
