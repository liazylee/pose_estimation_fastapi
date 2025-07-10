"""
Service Manager for RTMPose Service.
Manages multiple RTMPose service instances and their lifecycle.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from contanos.ai_service import BaseServiceManager, ServiceConfig
from service import RTMPoseService


# RTMPose服务配置
RTMPOSE_CONFIG = ServiceConfig(
    service_name="RTMPose Service",
    service_description="Microservice for RTMPose pose estimation with dynamic task_id support",
    service_version="1.0.0",
    default_host="0.0.0.0",
    default_port=8002,
    service_factory=RTMPoseService,
    topic_config={
        "input_frames": "raw_frames_{task_id}",
        "input_detections": "yolox_detections_{task_id}",
        "output": "rtmpose_results_{task_id}",
        "consumer_groups": [
            "rtmpose_raw_{task_id}",
            "rtmpose_det_{task_id}"
        ]
    }
)


class ServiceManager(BaseServiceManager):
    """RTMPose specific service manager."""

    def __init__(self):
        super().__init__(RTMPOSE_CONFIG)


# Global service manager instance
_service_manager = None


def get_service_manager() -> ServiceManager:
    """Get the global service manager instance."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
