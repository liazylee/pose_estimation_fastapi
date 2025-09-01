#!/usr/bin/env python3
"""
RTMPose Worker for pose estimation processing.
"""
import logging
from typing import Dict, Optional, List

import numpy as np

from apps.rtmpose_service.multiGPURTMpose import MultiGPURTMPose as RTMPose
from contanos import deserialize_image_from_kafka
from contanos.base_worker import BaseWorker

# from rtmlib.tools.pose_estimation import RTMPose  # noqa: F401

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
            # if self.device.startswith('cuda:'):
            #     device = 'cuda'
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
            tracked_poses = inputs.get('tracked_poses', [])
            if not isinstance(tracked_poses, List):
                logger.error(f"Worker {self.worker_id} received invalid detections format: {type(tracked_poses)}")
                return None
            detections = [i.get('bbox', []) for i in tracked_poses]
            pose_output, _ = self.pose_model(deserializer_frame, detections)
            if pose_output is None or len(pose_output) == 0:
                logger.warning(f"Worker {self.worker_id} received empty pose output")
                return None
            pose_output = np.array(pose_output).tolist()
            # match pose output with detection IDs
            if len(pose_output) != len(tracked_poses):
                logger.warning(f"Worker {self.worker_id} pose output length mismatch: "
                               f"{len(pose_output)} vs {len(tracked_poses)}")
                min_length = min(len(pose_output), len(tracked_poses))
                pose_output = pose_output[:min_length]
                tracked_poses = tracked_poses[:min_length]
            for i, pose in enumerate(pose_output):
                tracked_poses[i]['pose'] = pose
            return {
                'pose_estimations': pose_output,
                'frame_id': inputs.get('frame_id', None),
                'task_id': inputs.get('task_id', None),
                'pose_estimation_length': len(pose_output),
                'tracked_poses_results': tracked_poses
            }

        except Exception as e:
            logger.error(f"RTMPoseWorker {self.worker_id} prediction error: {e}")
            return None
