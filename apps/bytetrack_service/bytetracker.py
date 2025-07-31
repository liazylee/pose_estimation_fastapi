#!/usr/bin/env python3
"""
ByteTracker implementation for multi-object tracking.
Assigns stable IDs to detected persons across video frames.
"""
import logging
from typing import List, Dict, Any, Tuple

import numpy as np


class TrackState:
    """Enumeration for track states."""
    NEW = 0
    TRACKED = 1
    LOST = 2
    REMOVED = 3


class STrack:
    """Single track representation."""

    shared_kalman = None
    track_id_count = 0

    def __init__(self, bbox: List[float], score: float, frame_id: int):
        """Initialize a single track.
        
        Args:
            bbox: Bounding box in format [x1, y1, x2, y2]
            score: Detection confidence score
            frame_id: Current frame ID
        """
        # Bounding box and score
        self._bbox = np.array(bbox, dtype=np.float32)
        self.score = score

        # Track state
        self.track_id = None
        self.state = TrackState.NEW
        self.is_activated = False

        # Frame tracking
        self.frame_id = frame_id
        self.start_frame = frame_id
        self.tracklet_len = 0

        # History for smoothing
        self.history = []

    @property
    def bbox(self) -> np.ndarray:
        """Get current bounding box."""
        return self._bbox.copy()

    @property
    def center(self) -> np.ndarray:
        """Get center point of bounding box."""
        return np.array([(self._bbox[0] + self._bbox[2]) / 2,
                         (self._bbox[1] + self._bbox[3]) / 2])

    @property
    def area(self) -> float:
        """Get area of bounding box."""
        return (self._bbox[2] - self._bbox[0]) * (self._bbox[3] - self._bbox[1])

    def activate(self, frame_id: int) -> None:
        """Activate track and assign ID."""
        STrack.track_id_count += 1
        self.track_id = STrack.track_id_count
        self.tracklet_len = 0
        self.state = TrackState.TRACKED
        self.is_activated = True
        self.frame_id = frame_id

    def predict(self) -> None:
        """Predict next position (simple linear prediction)."""
        if len(self.history) >= 2:
            # Simple linear motion prediction
            prev_center = self.history[-1]
            curr_center = self.center
            velocity = curr_center - prev_center
            predicted_center = curr_center + velocity

            # Update bbox with predicted center
            width = self._bbox[2] - self._bbox[0]
            height = self._bbox[3] - self._bbox[1]
            self._bbox[0] = predicted_center[0] - width / 2
            self._bbox[1] = predicted_center[1] - height / 2
            self._bbox[2] = predicted_center[0] + width / 2
            self._bbox[3] = predicted_center[1] + height / 2

    def update(self, new_track, frame_id: int) -> None:
        """Update track with new detection."""
        self.frame_id = frame_id
        self.tracklet_len += 1

        # Store current center in history
        self.history.append(self.center)
        if len(self.history) > 10:  # Keep last 10 positions
            self.history.pop(0)

        # Update bbox and score
        self._bbox = np.array(new_track.bbox, dtype=np.float32)
        self.score = new_track.score

        self.state = TrackState.TRACKED
        self.is_activated = True

    def mark_lost(self) -> None:
        """Mark track as lost."""
        self.state = TrackState.LOST

    def mark_removed(self) -> None:
        """Mark track as removed."""
        self.state = TrackState.REMOVED


def iou_distance(track_bboxes: np.ndarray, det_bboxes: np.ndarray) -> np.ndarray:
    """Calculate IoU distance matrix between tracks and detections.
    
    Args:
        track_bboxes: Array of track bboxes, shape (M, 4)
        det_bboxes: Array of detection bboxes, shape (N, 4)
        
    Returns:
        Distance matrix of shape (M, N) where 0 = perfect match, 1 = no overlap
    """
    if len(track_bboxes) == 0 or len(det_bboxes) == 0:
        return np.empty((len(track_bboxes), len(det_bboxes)), dtype=np.float32)

    # Calculate intersection
    ious = np.zeros((len(track_bboxes), len(det_bboxes)), dtype=np.float32)

    for i, track_bbox in enumerate(track_bboxes):
        for j, det_bbox in enumerate(det_bboxes):
            # Calculate intersection
            x1 = max(track_bbox[0], det_bbox[0])
            y1 = max(track_bbox[1], det_bbox[1])
            x2 = min(track_bbox[2], det_bbox[2])
            y2 = min(track_bbox[3], det_bbox[3])

            if x1 < x2 and y1 < y2:
                intersection = (x2 - x1) * (y2 - y1)

                # Calculate union
                area1 = (track_bbox[2] - track_bbox[0]) * (track_bbox[3] - track_bbox[1])
                area2 = (det_bbox[2] - det_bbox[0]) * (det_bbox[3] - det_bbox[1])
                union = area1 + area2 - intersection

                if union > 0:
                    ious[i, j] = intersection / union

    # Convert IoU to distance (1 - IoU)
    return 1 - ious


def linear_assignment(cost_matrix: np.ndarray, thresh: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simple greedy matching algorithm.
    
    Args:
        cost_matrix: Cost matrix of shape (M, N)
        thresh: Maximum cost threshold for valid matches
        
    Returns:
        Tuple of (matches, unmatched_tracks, unmatched_detections)
    """
    if cost_matrix.size == 0:
        return np.empty((0, 2), dtype=int), np.arange(cost_matrix.shape[0]), np.arange(cost_matrix.shape[1])

    matches = []
    unmatched_tracks = list(range(cost_matrix.shape[0]))
    unmatched_dets = list(range(cost_matrix.shape[1]))

    # Greedy assignment
    while len(unmatched_tracks) > 0 and len(unmatched_dets) > 0:
        # Find minimum cost in remaining matrix
        min_cost = float('inf')
        min_track_idx = -1
        min_det_idx = -1

        for t_idx in unmatched_tracks:
            for d_idx in unmatched_dets:
                if cost_matrix[t_idx, d_idx] < min_cost:
                    min_cost = cost_matrix[t_idx, d_idx]
                    min_track_idx = t_idx
                    min_det_idx = d_idx

        # If cost is below threshold, create match
        if min_cost < thresh:
            matches.append([min_track_idx, min_det_idx])
            unmatched_tracks.remove(min_track_idx)
            unmatched_dets.remove(min_det_idx)
        else:
            break

    return np.array(matches), np.array(unmatched_tracks), np.array(unmatched_dets)


class ByteTracker:
    """ByteTrack multi-object tracker implementation."""

    def __init__(self, track_thresh: float = 0.5, track_buffer: int = 30,
                 match_thresh: float = 0.8, frame_rate: int = 30):
        """Initialize ByteTracker.
        
        Args:
            track_thresh: Detection threshold for tracking
            track_buffer: Number of frames to keep lost tracks
            match_thresh: Matching threshold for IoU distance
            frame_rate: Video frame rate
        """
        self.track_thresh = track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.frame_rate = frame_rate

        self.frame_id = 0
        self.tracked_tracks = []
        self.lost_tracks = []
        self.removed_tracks = []

        logging.info(f"ByteTracker initialized with thresh={track_thresh}, buffer={track_buffer}")

    def update(self, detections: List[Dict[str, Any]], frame_id: int) -> List[Dict[str, Any]]:
        """Update tracker with new detections.
        
        Args:
            detections: List of detection dicts with 'bbox' and 'confidence' keys
            frame_id: Current frame ID
            
        Returns:
            List of tracked objects with stable track IDs
        """
        self.frame_id = frame_id

        # Convert detections to STrack objects
        det_tracks = []
        for det in detections:
            bbox = det['bbox']
            confidence = det.get('confidence', 1.0)

            # Only process detections above threshold
            if confidence >= self.track_thresh:
                det_tracks.append(STrack(bbox, confidence, frame_id))

        # Split tracked tracks into activated and lost
        activated_tracks = [t for t in self.tracked_tracks if t.is_activated]
        lost_tracks = [t for t in self.tracked_tracks if not t.is_activated]

        # Predict positions for existing tracks
        for track in activated_tracks:
            track.predict()

        # First association with high confidence detections
        if len(activated_tracks) > 0 and len(det_tracks) > 0:
            track_bboxes = np.array([t.bbox for t in activated_tracks])
            det_bboxes = np.array([t.bbox for t in det_tracks])
            cost_matrix = iou_distance(track_bboxes, det_bboxes)

            matches, unmatched_tracks, unmatched_dets = linear_assignment(
                cost_matrix, self.match_thresh)
        else:
            matches = np.empty((0, 2), dtype=int)
            unmatched_tracks = np.arange(len(activated_tracks))
            unmatched_dets = np.arange(len(det_tracks))

        # Update matched tracks
        for m in matches:
            track_idx, det_idx = m[0], m[1]
            activated_tracks[track_idx].update(det_tracks[det_idx], frame_id)

        # Handle unmatched tracks
        for track_idx in unmatched_tracks:
            track = activated_tracks[track_idx]
            track.mark_lost()
            lost_tracks.append(track)

        # Initialize new tracks from unmatched detections
        new_tracks = []
        for det_idx in unmatched_dets:
            det_track = det_tracks[det_idx]
            det_track.activate(frame_id)
            new_tracks.append(det_track)

        # Update tracked tracks
        self.tracked_tracks = [t for t in activated_tracks if t.state == TrackState.TRACKED]
        self.tracked_tracks.extend(new_tracks)

        # Remove old lost tracks
        self.lost_tracks = [t for t in lost_tracks
                            if frame_id - t.frame_id <= self.track_buffer]

        # Prepare output
        output_tracks = []
        for track in self.tracked_tracks:
            if track.is_activated:
                output_tracks.append({
                    'track_id': track.track_id,
                    'bbox': track.bbox.tolist(),
                    'score': track.score
                })

        logging.debug(f"Frame {frame_id}: {len(output_tracks)} tracked objects")
        return output_tracks

    def reset(self) -> None:
        """Reset tracker state."""
        STrack.track_id_count = 0
        self.frame_id = 0
        self.tracked_tracks = []
        self.lost_tracks = []
        self.removed_tracks = []
        logging.info("ByteTracker reset")
