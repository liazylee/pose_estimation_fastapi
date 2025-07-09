#!/usr/bin/env python3
"""
RTMPose Worker for pose estimation processing.
"""
import logging
from typing import Dict, Optional, List

import numpy as np
from rtmlib.tools.pose_estimation import RTMPose

from contanos import deserialize_image_from_kafka
from contanos.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class RTMPoseWorker(BaseWorker):
    """RTMPose pose estimation worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        super().__init__(worker_id, device, model_config,
                         input_interface, output_interface)

        self.pose_model = None
        logger.info(f"RTMPoseWorker {worker_id} initialized on device {device}")
        self._model_init()

    def _model_init(self):
        """Initialize the RTMPose model."""
        try:
            device = self.device
            if self.device.startswith('cuda:'):
                device = 'cuda'
            model_config = self.model_config
            self.pose_model = RTMPose(**model_config, device=device)

            logger.info(f"RTMPose model initialized successfully on device: {device}")

        except Exception as e:
            logger.error(f"Failed to initialize RTMPose model: {e}")
            raise

    def _predict(self, inputs: Dict) -> Optional[Dict]:
        """Run RTMPose estimation on input frame."""
        try:
            frame = inputs.get('image_bytes')
            if frame is None:
                logger.error(f"Worker {self.worker_id} received empty input frame")
                return None

            # Run model inference
            deserializer_frame = deserialize_image_from_kafka(frame)
            detections = inputs.get('detections', {})
            if not isinstance(detections, List):
                logger.error(f"Worker {self.worker_id} received invalid detections format: {type(detections)}")
                return None
            pose_output, _ = self.pose_model(deserializer_frame, detections)
            if pose_output is None or len(pose_output) == 0:
                logger.warning(f"Worker {self.worker_id} received empty pose output")
                return None
            pose_output = np.array(pose_output).tolist()
            return {
                'pose_estimations': pose_output,
                'frame_id': inputs.get('frame_id', None),
                'task_id': inputs.get('task_id', None),
                'pose_estimation_length': len(pose_output),
            }

        except Exception as e:
            logger.error(f"RTMPoseWorker {self.worker_id} prediction error: {e}")
            return None
