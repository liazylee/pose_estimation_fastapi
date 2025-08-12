#!/usr/bin/env python3
"""
BoTSORT Worker using contanos framework with ByteTracker fallback.
Optimized for pose estimation pipeline with stable track ID assignment.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
from contanos import deserialize_image_from_kafka

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.base_worker import BaseWorker

# Import BoTSORT from boxmot
try:
    from boxmot import BotSort
except ImportError as e:
    logging.error(f"Failed to import BoTSORT from boxmot: {e}")
    logging.error("Please install boxmot: pip install boxmot")
    raise

# Import ByteTracker as fallback
try:
    from .bytetracker import ByteTracker
except ImportError:
    try:
        from bytetracker import ByteTracker
    except ImportError:
        from apps.bytetrack_service.bytetracker import ByteTracker


class ByteTrackWorker(BaseWorker):
    """BoTSORT tracking worker with ByteTracker fallback for pose estimation pipeline."""

    def __init__(self, worker_id: int, device: str, model_config: Dict, 
                 input_interface, output_interface):
        super().__init__(worker_id, device, model_config, input_interface, output_interface)
        
        self.current_task_id = None
        self.tracker = None
        self.tracker_type = "unknown"
        
        logging.info(f"BoTSORT Worker {worker_id} initializing on device {device}")
        self._model_init()

    def _model_init(self):
        """Initialize BoTSORT with fallback to ByteTracker."""
        try:
            # Initialize BoTSORT
            reid_weights_str = self.model_config.get('reid_weights', 'osnet_x0_25_msmt17.pt')
            reid_weights_path = None
            
            if reid_weights_str:
                reid_weights_path = Path(reid_weights_str)
                if not reid_weights_path.exists():
                    logging.warning(f"ReID weights not found: {reid_weights_path}, using BoTSORT without ReID")
                    reid_weights_path = None

            self.tracker = BotSort(
                reid_weights=reid_weights_path,
                device=self.device,
                half=self.model_config.get('half', True),
                track_high_thresh=self.model_config.get('track_high_thresh', 0.3),
                track_low_thresh=self.model_config.get('track_low_thresh', 0.1),
                new_track_thresh=self.model_config.get('new_track_thresh', 0.4),
                track_buffer=self.model_config.get('track_buffer', 30),
                match_thresh=self.model_config.get('match_thresh', 0.8),
                cmc_method=self.model_config.get('cmc_method', 'ecc'),
            )
            self.tracker_type = "BoTSORT"
            logging.info(f"BoTSORT initialized on {self.device}")
            
        except Exception as e:
            logging.error(f"BoTSORT initialization failed: {e}, falling back to ByteTracker")
            
            try:
                self.tracker = ByteTracker(
                    track_thresh=self.model_config.get('track_high_thresh', 0.3),
                    track_buffer=self.model_config.get('track_buffer', 30),
                    match_thresh=self.model_config.get('match_thresh', 0.8),
                    frame_rate=self.model_config.get('frame_rate', 25)
                )
                self.tracker_type = "ByteTracker"
                logging.info(f"ByteTracker fallback initialized")
                
            except Exception as fallback_e:
                logging.error(f"Both BoTSORT and ByteTracker failed: {e}, {fallback_e}")
                raise Exception("Tracker initialization failed")
        
        if self.tracker is None:
            raise Exception("Tracker is None after initialization")

    def _predict(self, inputs: Dict) -> Any:
        """
        Perform tracking on detected objects.
        
        Args:
            inputs: Input data containing frame and detections
            
        Returns:
            Tracking results with stable track IDs
        """
        try:
            # Extract input data
            frame_bytes = inputs.get('image_bytes')
            frame = deserialize_image_from_kafka(frame_bytes)
            detections_list = inputs.get("detections", [])
            task_id = inputs.get('task_id')
            frame_id = inputs.get('frame_id', 0)
            timestamp = inputs.get('timestamp')
            
            # Convert detections to numpy format: [x1, y1, x2, y2, score, class_id]
            if len(detections_list) > 0:
                detections = np.array([
                    det.get('bbox', [0, 0, 0, 0]) + [det.get('score', 0.0), det.get('class_id', 0)]
                    for det in detections_list
                ], dtype=np.float32)
            else:
                detections = np.empty((0, 6), dtype=np.float32)
            
            # Check tracker initialization
            if self.tracker is None:
                logging.error(f"Worker {self.worker_id}: Tracker not initialized")
                return self._empty_result(task_id, frame_id, timestamp)
            
            # Perform tracking based on tracker type
            if self.tracker_type == "BoTSORT":
                tracks = self._track_with_botsort(detections, frame)
            elif self.tracker_type == "ByteTracker":
                tracks = self._track_with_bytetracker(detections_list, frame_id)
            else:
                logging.error(f"Unknown tracker type: {self.tracker_type}")
                return self._empty_result(task_id, frame_id, timestamp)
            
            return {
                "task_id": task_id,
                "frame_id": frame_id,
                "timestamp": timestamp,
                "tracked_poses": tracks
            }
            
        except Exception as e:
            logging.error(f"Worker {self.worker_id} ({self.tracker_type}) prediction error: {e}")
            return self._empty_result(
                inputs.get('task_id'), 
                inputs.get('frame_id', 0), 
                inputs.get('timestamp')
            )

    def _track_with_botsort(self, detections: np.ndarray, frame: np.ndarray) -> list:
        """Track using BoTSORT."""
        if frame is None:
            logging.warning("Frame is None for BoTSORT tracking")
            return []
        
        outputs = self.tracker.update(detections, frame)
        
        tracks = []
        if outputs is not None:
            for output in outputs:
                if len(output) >= 7:
                    x1, y1, x2, y2, tid, cls, score = output[:7]
                    tracks.append({
                        "track_id": int(tid),
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "score": float(score),
                        "class_id": int(cls)
                    })
        
        return tracks

    def _track_with_bytetracker(self, detections_list: list, frame_id: int) -> list:
        """Track using ByteTracker."""
        # Convert to ByteTracker format
        bytetrack_detections = []
        for det in detections_list:
            bytetrack_detections.append({
                'bbox': det.get('bbox', [0, 0, 0, 0]),
                'confidence': det.get('score', 0.0),
                'class_id': det.get('class_id', 0)
            })
        
        tracked_objects = self.tracker.update(bytetrack_detections, frame_id)
        
        tracks = []
        for obj in tracked_objects:
            tracks.append({
                "track_id": obj['track_id'],
                "bbox": obj['bbox'],
                "score": obj['score'],
                "class_id": obj.get('class_id', 0)
            })
        
        return tracks

    def _empty_result(self, task_id, frame_id, timestamp):
        """Return empty tracking result."""
        return {
            'task_id': task_id,
            'frame_id': frame_id,
            'timestamp': timestamp,
            'tracked_poses': []
        }