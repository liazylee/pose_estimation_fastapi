"""
Simple FrameAnnotator for drawing pose keypoints and bounding boxes.
Follows KISS principles - simple, direct, maintainable code.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

from contanos.visualizer.box_drawer import draw_boxes_on_frame
from contanos.visualizer.skeleton_drawer import draw_pose


class FrameAnnotator:
    """Annotates video frames with pose keypoints and tracking data."""

    def __init__(self, line_thickness=1, keypoint_radius=1, bbox_thickness=1):
        """Initialize FrameAnnotator with drawing parameters."""
        self.line_thickness = line_thickness
        self.keypoint_radius = keypoint_radius
        self.bbox_thickness = bbox_thickness
        self.logger = logging.getLogger(__name__)

    def annotate_frame(self, frame: np.ndarray,
                       tracked_objects: Optional[List[Dict[str, Any]]] = None,
                       poses: List[List[Tuple[float, float]]] = None) -> np.ndarray:
        """Annotate frame with poses and tracking data.
        
        Args:
            frame: Input frame to annotate
            tracked_objects: List of tracked objects with bbox, track_id, and pose_keypoints
            poses: Standalone pose keypoints (fallback if no tracking)
            
        Returns:
            Annotated frame
        """
        if frame is None:
            self.logger.error("Invalid frame input")
            return np.zeros((480, 640, 3), dtype=np.uint8)

        result_frame = frame.copy()

        # Primary: Use tracked objects (with integrated pose data)
        result_frame = draw_boxes_on_frame(result_frame, tracked_objects, scale=1.0, draw_labels=True)

        result_frame = draw_pose(result_frame, poses, )
        return result_frame
