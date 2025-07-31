from contanos.ai_service import BaseServiceManager, ServiceConfig
from service import ByteTrackService

ByteTrack_CONFIG = ServiceConfig(
    service_name="ByteTrack Detection Service",
    service_description="Microservice for ByteTrack object detection with dynamic task_id support",
    service_version="1.0.0",
    default_host="0.0.0.0",
    default_port=8003,
    service_factory=ByteTrackService,
    topic_config={
        "input": "yolox_detections_{task_id}",
        "output": "bytetrack_tracking_{task_id}",
        "consumer_group": "bytetrack_consumers_{task_id}"
    }
)


class ServiceManager(BaseServiceManager):
    """ByteTrack specific service manager."""

    def __init__(self):
        super().__init__(ByteTrack_CONFIG)


# singleton instance of ServiceManager
_service_manager = None


def get_service_manager():
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
