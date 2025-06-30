# Video Annotation Rendering
# Functions for drawing pose keypoints, bounding boxes, and track IDs

# TODO: Implement the following rendering functions:
# - draw_pose_keypoints(frame, keypoints, track_id): Draw skeleton on frame
# - draw_bounding_box(frame, bbox, track_id): Draw detection box
# - draw_track_id(frame, position, track_id): Draw track ID text
# - apply_pose_colors(keypoints, track_id): Color-code different persons
# - render_frame_annotations(frame, tracked_poses): Main rendering function

# TODO: Add configurable rendering styles and colors
# TODO: Implement pose connection lines and joint visualization
# TODO: Add performance optimizations for real-time rendering 
"""
Pose rendering utilities for drawing keypoints and skeletons.
"""
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PoseRenderer:
    """Renders pose keypoints and skeletons on frames."""
    
    # COCO skeleton connections
    SKELETON_CONNECTIONS = [
        (0, 1), (0, 2), (1, 3), (2, 4),  # Head
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # Arms
        (5, 11), (6, 12), (11, 12),  # Torso
        (11, 13), (13, 15), (12, 14), (14, 16)  # Legs
    ]
    
    # Color palette for track IDs
    COLORS = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (255, 0, 255), (0, 255, 255),
        (128, 255, 0), (255, 128, 0), (128, 0, 255),
        (255, 0, 128), (0, 128, 255), (0, 255, 128)
    ]
    
    def __init__(self, config: Dict):
        self.show_track_id = config.get('show_track_id', True)
        self.show_keypoints = config.get('show_keypoints', True)
        self.show_skeleton = config.get('show_skeleton', True)
        self.keypoint_radius = config.get('keypoint_radius', 3)
        self.skeleton_thickness = config.get('skeleton_thickness', 2)
        self.font_scale = config.get('font_scale', 0.5)
        self.font_thickness = config.get('font_thickness', 1)
        self.confidence_threshold = config.get('confidence_threshold', 0.5)
    
    def render_frame(self, 
                    frame: np.ndarray, 
                    tracked_poses: List[Dict],
                    metadata: Optional[Dict] = None) -> np.ndarray:
        """
        Render poses on a frame.
        
        Args:
            frame: Input frame (RGB)
            tracked_poses: List of tracked pose data
            metadata: Optional frame metadata
            
        Returns:
            Annotated frame
        """
        # Create a copy to avoid modifying the original
        annotated = frame.copy()
        
        for pose_data in tracked_poses:
            track_id = pose_data.get('track_id', -1)
            keypoints = pose_data.get('keypoints', [])
            
            if not keypoints:
                continue
            
            # Get color for this track
            color = self.COLORS[track_id % len(self.COLORS)]
            
            # Draw skeleton
            if self.show_skeleton:
                self._draw_skeleton(annotated, keypoints, color)
            
            # Draw keypoints
            if self.show_keypoints:
                self._draw_keypoints(annotated, keypoints, color)
            
            # Draw track ID
            if self.show_track_id and track_id >= 0:
                self._draw_track_id(annotated, keypoints, track_id, color)
        
        # Add metadata overlay if provided
        if metadata:
            self._draw_metadata(annotated, metadata)
        
        return annotated
    
    def _draw_keypoints(self, 
                       frame: np.ndarray, 
                       keypoints: List[List[float]], 
                       color: Tuple[int, int, int]):
        """Draw keypoint circles."""
        for kpt in keypoints:
            if len(kpt) >= 3:
                x, y, conf = int(kpt[0]), int(kpt[1]), kpt[2]
                if conf > self.confidence_threshold:
                    cv2.circle(frame, (x, y), self.keypoint_radius, color, -1)
                    # White border for visibility
                    cv2.circle(frame, (x, y), self.keypoint_radius, (255, 255, 255), 1)
    
    def _draw_skeleton(self, 
                      frame: np.ndarray, 
                      keypoints: List[List[float]], 
                      color: Tuple[int, int, int]):
        """Draw skeleton connections."""
        for connection in self.SKELETON_CONNECTIONS:
            kpt1_idx, kpt2_idx = connection
            
            if kpt1_idx < len(keypoints) and kpt2_idx < len(keypoints):
                kpt1 = keypoints[kpt1_idx]
                kpt2 = keypoints[kpt2_idx]
                
                if (len(kpt1) >= 3 and len(kpt2) >= 3 and
                    kpt1[2] > self.confidence_threshold and 
                    kpt2[2] > self.confidence_threshold):
                    
                    pt1 = (int(kpt1[0]), int(kpt1[1]))
                    pt2 = (int(kpt2[0]), int(kpt2[1]))
                    cv2.line(frame, pt1, pt2, color, self.skeleton_thickness)
    
    def _draw_track_id(self, 
                      frame: np.ndarray, 
                      keypoints: List[List[float]], 
                      track_id: int, 
                      color: Tuple[int, int, int]):
        """Draw track ID above the person."""
        # Find the topmost keypoint (usually head)
        valid_keypoints = [kpt for kpt in keypoints if len(kpt) >= 3 and kpt[2] > 0]
        
        if valid_keypoints:
            # Get topmost point
            top_point = min(valid_keypoints, key=lambda k: k[1])
            x, y = int(top_point[0]), int(top_point[1])
            
            # Draw background rectangle
            text = f"ID: {track_id}"
            (text_width, text_height), baseline = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, self.font_scale, self.font_thickness
            )
            
            cv2.rectangle(frame, 
                         (x - 5, y - text_height - 10),
                         (x + text_width + 5, y - 5),
                         color, -1)
            
            # Draw text
            cv2.putText(frame, text, (x, y - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, self.font_scale,
                       (255, 255, 255), self.font_thickness)
    
    def _draw_metadata(self, frame: np.ndarray, metadata: Dict):
        """Draw metadata overlay."""
        height, width = frame.shape[:2]
        
        # Create semi-transparent overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (300, 80), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
        
        # Draw metadata text
        y_offset = 30
        cv2.putText(frame, f"FPS: {metadata.get('fps', 'N/A')}", 
                   (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        y_offset += 20
        cv2.putText(frame, f"Frame: {metadata.get('frame_id', 'N/A')}", 
                   (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        y_offset += 20
        cv2.putText(frame, f"People: {len(metadata.get('tracked_poses', []))}", 
                   (20, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)