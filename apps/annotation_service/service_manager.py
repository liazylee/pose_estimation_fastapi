"""
Service Manager for Annotation Service.
Manages multiple annotation service instances and their lifecycle.
"""

from contanos.ai_service import BaseServiceManager, ServiceConfig
from service import AnnotationService

# Annotation服务配置
ANNOTATION_CONFIG = ServiceConfig(
    service_name="Annotation Service",
    service_description="Microservice for video annotation with detection overlays and RTSP output",
    service_version="1.0.0",
    default_host="0.0.0.0",
    default_port=8004,
    service_factory=AnnotationService,
    topic_config={
        "inputs": {
            "raw_frames": "raw_frames_{task_id}",
            "detections": "yolox_detections_{task_id}",
            "poses": "rtmpose_results_{task_id}"
        },
        "outputs": {
            "rtsp_stream": "rtsp://localhost:8554/outstream_{task_id}",
            "video_file": "output_videos/{task_id}/annotated_{task_id}_[timestamp].mp4",
            "debug_frames": "debug_frames/{task_id}/"
        },
        "consumer_groups": [
            "annotation_raw_{task_id}",
            "annotation_track_{task_id}",
            "annotation_pose_{task_id}"
        ]
    }
)


class ServiceManager(BaseServiceManager):
    """Annotation specific service manager."""

    def __init__(self):
        super().__init__(ANNOTATION_CONFIG)


# Global service manager instance
_service_manager = None


def get_service_manager() -> ServiceManager:
    """Get the global service manager instance."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
