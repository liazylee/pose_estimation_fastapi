#!/usr/bin/env python3
"""
ByteTrack Worker using contanos framework.
"""
import logging
import os
import sys
from typing import Any, Dict

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.base_worker import BaseWorker

# Import ByteTracker with error handling for different execution contexts
try:
    from .bytetracker import ByteTracker
except ImportError:
    try:
        from bytetracker import ByteTracker
    except ImportError:
        from apps.bytetrack_service.bytetracker import ByteTracker


class ByteTrackWorker(BaseWorker):
    """ByteTrack tracking worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        super().__init__(worker_id, device, model_config,
                         input_interface, output_interface)

        # Store current task_id for track management per task
        self.current_task_id = None
        self.tracker = None

        logging.info(f"ByteTrackWorker {worker_id} initialized on device {device}")

    def _model_init(self):
        """Initialize the ByteTrack model."""
        try:
            # Extract tracking parameters from model config
            track_thresh = self.model_config.get('track_thresh', 0.5)
            track_buffer = self.model_config.get('track_buffer', 30)
            match_thresh = self.model_config.get('match_thresh', 0.8)
            frame_rate = self.model_config.get('frame_rate', 30)

            # ByteTracker doesn't need a specific model, just algorithm parameters
            self.model = None  # Not used for ByteTrack

            logging.info(f"ByteTrackWorker {self.worker_id} initialized with "
                         f"track_thresh={track_thresh}, match_thresh={match_thresh}")

        except Exception as e:
            logging.error(f"Failed to initialize ByteTrack worker {self.worker_id}: {e}")
            raise

    def _predict(self, inputs: Dict) -> Any:
        """
        Perform tracking on input detection data.
        
        Args:
            input: Input detection data from YOLOX
            metadata: Metadata containing frame info
            
        Returns:
            Tracking results with stable track IDs
        """
        try:

            task_id = inputs.get('task_id', None),
            frame_id: int = inputs.get('frame_id', 0)
            # Initialize or reset tracker for new task
            if task_id != self.current_task_id:
                self.current_task_id = task_id
                # Extract tracking parameters from model config
                track_thresh = self.model_config.get('track_thresh', 0.5)
                track_buffer = self.model_config.get('track_buffer', 30)
                match_thresh = self.model_config.get('match_thresh', 0.8)
                frame_rate = self.model_config.get('frame_rate', 25)

                self.tracker = ByteTracker(
                    track_thresh=track_thresh,
                    track_buffer=track_buffer,
                    match_thresh=match_thresh,
                    frame_rate=frame_rate
                )
                logging.info(f"Created new ByteTracker for task {task_id}")

            # Extract detections from input
            detections = inputs.get('detections', [])
            if not detections:
                logging.warning(f"ByteTrackWorker {self.worker_id} received empty detections for frame {frame_id}")
                return {
                    'task_id': task_id,
                    'frame_id': frame_id,
                    'tracked_poses': []
                }
            # Update tracker with detections
            tracked_objects = self.tracker.update(detections, frame_id)

            # Format output according to schema
            result = {
                'task_id': task_id,
                'frame_id': frame_id,

                'tracked_poses': [
                    {
                        'track_id': obj['track_id'],
                        'bbox': obj['bbox'],
                        'score': obj['score'],
                    }
                    for obj in tracked_objects
                ]
            }

            logging.debug(f"ByteTrackWorker {self.worker_id} processed frame {frame_id}: "
                          f"{len(tracked_objects)} tracked objects")

            return result

        except Exception as e:
            logging.error(f"ByteTrackWorker {self.worker_id} prediction error: {e}")
            # Return empty result on error
            return {
                'task_id': inputs.get('task_id', None),
                'frame_id': inputs.get('frame_id', 0),
                'timestamp': inputs.get('timestamp', None),
                'tracked_poses': []
            }
