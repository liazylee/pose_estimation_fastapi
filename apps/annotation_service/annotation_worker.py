"""
annotation worker.py
"""
import logging
import os
from typing import Dict, Optional

import cv2
import numpy as np

from contanos import BaseWorker, deserialize_image_from_kafka
from contanos.visualizer.trajectory_drawer import TrajectoryDrawer

# Import FrameAnnotator with error handling for different execution contexts
try:
    from .frame_annotator import FrameAnnotator
except ImportError:
    try:
        from frame_annotator import FrameAnnotator
    except ImportError:
        from apps.annotation_service.frame_annotator import FrameAnnotator


class AnnotationWorker(BaseWorker):
    """Annotation worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        BaseWorker.__init__(self, worker_id, device, model_config,
                            input_interface, output_interface)

        # Processing state
        self.frame_count = 0

        logging.info(f"AnnotationWorker {worker_id} initialized on device {device}")

    def _model_init(self):
        """Initialize the annotation model."""
        try:
            # Initialize FrameAnnotator
            self.frame_annotator = FrameAnnotator(
            )
            self.trajectory_drawer = TrajectoryDrawer(
                max_trajectory_length=20,
                gap_threshold=75.0,
            )

            logging.info(f"AnnotationWorker {self.worker_id} model initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize annotation model for worker {self.worker_id}: {e}")
            raise

    def _predict(self, inputs: Dict) -> Optional[Dict]:
        """
        Annotate the input frame with all available data.

        Args:
            inputs (Dict): Input data containing 'image_bytes', 'detections', 'poses', and 'tracked_poses'.

        Returns:
            Dict: Result data for output interfaces.
        """
        try:
            frame_bytes = inputs.get('image_bytes')
            # detections = inputs.get('detections', [])
            poses = inputs.get('pose_estimations', [])  # Support both field names
            tracked_poses = inputs.get('tracked_poses', [])
            tracked_poses_results = inputs.get('tracked_poses_results', [])
            frame_id = inputs.get('frame_id', 0)
            if frame_bytes is None:
                logging.error(f"Worker {self.worker_id}: Invalid frame input")
                return None

            # Deserialize frame from Kafka
            frame = deserialize_image_from_kafka(frame_bytes)
            if frame is None or not isinstance(frame, np.ndarray):
                logging.error(f"Worker {self.worker_id}: Failed to deserialize frame")
                return None
            points = {
                obj['track_id']: (
                    obj['bbox'][2],
                    obj['bbox'][3]
                )
                for obj in tracked_poses
            }
            self.trajectory_drawer.update_trajectories(points, frame_id)
            # Use FrameAnnotator to draw all annotations
            self.trajectory_drawer.purge_stale_trajectories(frame_id)

            annotated_frame = self.frame_annotator.annotate_frame(
                frame=frame,
                tracked_objects=tracked_poses,
                poses=poses,

            )
            # use TrajectoryDrawer
            annotated_frame = self.trajectory_drawer.draw_trajectories(annotated_frame)
            # Save debug frames periodically
            if self.frame_count % 100 == 0:
                # self._save_debug_frame(annotated_frame)
                pass
            self.frame_count += 1

            # Prepare return data
            result_data = {
                'results': {
                    'annotated_frame': annotated_frame
                },
                'frame_id': inputs.get('frame_id', None),
                'task_id': self.model_config.get('task_id', None),
                'timestamp': inputs.get('timestamp', None),
                'tracked_poses_results': tracked_poses_results,
            }

            return result_data

        except Exception as e:
            logging.error(f"AnnotationWorker {self.worker_id} prediction error: {e}")
            return None

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
            # Clean up MongoDB connection
            self.cleanup_mongo()
            logging.info(f"AnnotationWorker {self.worker_id} cleanup completed after {self.frame_count} frames")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

        super().cleanup()
