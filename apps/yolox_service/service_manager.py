# service_manager.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from contanos.ai_service import BaseServiceManager, ServiceConfig
from service import YOLOXService


# YOLOX服务配置
YOLOX_CONFIG = ServiceConfig(
    service_name="YOLOX Detection Service",
    service_description="Microservice for YOLOX object detection with dynamic task_id support",
    service_version="1.0.0",
    default_host="0.0.0.0",
    default_port=8001,
    service_factory=YOLOXService,
    topic_config={
        "input": "raw_frames_{task_id}",
        "output": "yolox_detections_{task_id}",
        "consumer_group": "yolox_consumers_{task_id}"
    }
)


class ServiceManager(BaseServiceManager):
    """YOLOX specific service manager."""
    
    def __init__(self):
        super().__init__(YOLOX_CONFIG)


# singleton instance of ServiceManager
_service_manager = None


def get_service_manager():
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
