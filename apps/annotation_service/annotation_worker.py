"""
annotation worker.py
"""
import logging
import os
from typing import Dict, Optional

import cv2
import numpy as np

from contanos import BaseWorker, deserialize_image_from_kafka
from contanos.visualizer.box_drawer import draw_boxes_on_frame
from contanos.visualizer.skeleton_drawer import draw_pose


class AnnotationWorker(BaseWorker):
    """Annotation worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        super().__init__(worker_id, device, model_config,
                         input_interface, output_interface)

        # Processing state
        self.frame_count = 0

        logging.info(f"AnnotationWorker {worker_id} initialized on device {device}")

    def _model_init(self):
        """Initialize the annotation model."""
        try:
            # Initialize drawing functions
            self.box_drawer = draw_boxes_on_frame
            self.skeleton_drawer = draw_pose

            logging.info(f"AnnotationWorker {self.worker_id} model initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize annotation model for worker {self.worker_id}: {e}")
            raise

    def _predict(self, inputs: Dict) -> Optional[Dict]:
        """
        Annotate the input frame with bounding boxes and pose data and send to output.

        Args:
            inputs (Dict): Input data containing 'image_bytes', 'detections', and 'pose_estimations'.

        Returns:
            Dict: Result data for output interfaces.
        """
        try:
            frame_bytes = inputs.get('image_bytes')
            detections = inputs.get('detections', [])
            # Fix field name mismatch: RTMPose outputs 'pose_estimations' (plural)
            pose_estimations = inputs.get('pose_estimations', [])

            if frame_bytes is None:
                logging.error(f"Worker {self.worker_id}: Invalid frame input")
                return None

            # Deserialize frame from Kafka
            frame = deserialize_image_from_kafka(frame_bytes)
            if frame is None or not isinstance(frame, np.ndarray):
                logging.error(f"Worker {self.worker_id}: Failed to deserialize frame")
                return None

            # Draw annotations
            annotated_frame = self._draw_annotations(frame, detections, pose_estimations)

            # Save debug frames periodically
            if self.frame_count % 100 == 0:
                self._save_debug_frame(annotated_frame)

            self.frame_count += 1

            # Convert BGR to RGB for output (standardized format)
            rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)

            # Return data formatted for output interfaces
            return {
                'results': {
                    'annotated_frame': rgb_frame
                },
                'frame_id': inputs.get('frame_id', None),
                'task_id': inputs.get('task_id', self.model_config.get('task_id'))
            }

        except Exception as e:
            logging.error(f"AnnotationWorker {self.worker_id} prediction error: {e}")
            return None

    def _draw_annotations(self, frame: np.ndarray, detections: list, pose_estimations: list = None) -> np.ndarray:
        """Draw annotations on the frame."""
        try:
            # Create a copy to avoid modifying the original frame
            annotated_frame = frame.copy()

            # Draw boxes using the existing box_drawer function
            if detections:
                logging.debug(f"Drawing {len(detections)} detection boxes")
                annotated_frame = self.box_drawer(
                    annotated_frame,
                    detections,
                    scale=1.0,
                    draw_labels=True
                )

            # Draw pose estimation if available
            if pose_estimations:
                logging.debug(f"Drawing pose estimation for {len(pose_estimations)} persons")
                annotated_frame = self.skeleton_drawer(
                    annotated_frame,
                    pose_estimations,
                )
            
            return annotated_frame

        except Exception as e:
            logging.error(f"Error drawing annotations: {e}")
            return frame

    def _save_debug_frame(self, frame: np.ndarray) -> None:
        """Save debug frame to local storage."""
        try:
            debug_dir = self.model_config.get('debug_output_dir', 'debug_frames')
            task_id = self.model_config.get('task_id', 'unknown')
            
            # Create task-specific debug directory
            full_debug_dir = os.path.join(debug_dir, task_id)
            os.makedirs(full_debug_dir, exist_ok=True)
            
            debug_frame_path = os.path.join(full_debug_dir, f"annotated_frame_{self.frame_count}.jpg")
            cv2.imwrite(debug_frame_path, frame)
            logging.info(f"Saved debug frame: {debug_frame_path}")
            
        except Exception as e:
            logging.error(f"Error saving debug frame: {e}")

    def cleanup(self):
        """Clean up resources when worker is shut down."""
        try:
            logging.info(f"AnnotationWorker {self.worker_id} cleanup completed after {self.frame_count} frames")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
        
        super().cleanup()
