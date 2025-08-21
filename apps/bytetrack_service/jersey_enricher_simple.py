#!/usr/bin/env python3
"""
Simplified Jersey Number Enricher
Synchronous implementation without async complexity.
"""

import logging
import time
from collections import deque
from enum import Enum
from typing import Dict, List, Any, Optional, Union

import numpy as np

from .helper import _parse_ts
from .jersey_ocr import JerseyOCRModel, extract_jersey_roi, check_roi_quality


class BindingState(Enum):
    """Track binding states for jersey numbers."""
    PENDING = "pending"
    LOCKED = "locked"
    STALE = "stale"


class SimpleTrackState:
    """Simplified state management for a single track."""

    def __init__(self, track_id: int, config: Dict):
        self.track_id = track_id
        self.config = config

        # State management
        self.state = BindingState.PENDING
        self.state_changed_at = time.time()

        # Jersey number state
        self.number_lock: Optional[str] = None
        self.jersey_score = 0.0

        # Simple buffering
        self.buffered_frames = deque()
        self.buffer_max_time = config.get('buffer_sec', 1.0)

        # OCR throttling
        self.last_ocr_time = 0.0
        self.last_ocr_frame = 0
        self.ocr_interval_frames = config.get('ocr_interval_frames', 15)
        self.ocr_interval_sec = config.get('ocr_interval_sec', 0.5)

        # Thresholds
        self.lock_score_thr = config.get('lock_score_thr', 0.7)
        self.stale_timeout_sec = config.get('stale_timeout_sec', 8.0)

        # Recent readings for stability
        self.recent_readings = deque(maxlen=5)  # Keep last 5 readings

    def should_trigger_ocr(self, frame_id: int, current_time: float) -> bool:
        """Check if OCR should be triggered."""
        # Frame interval check
        frame_interval_ok = (frame_id - self.last_ocr_frame) >= self.ocr_interval_frames

        # Time interval check  
        time_interval_ok = (current_time - self.last_ocr_time) >= self.ocr_interval_sec

        if frame_interval_ok or time_interval_ok:
            self.last_ocr_frame = frame_id
            self.last_ocr_time = current_time
            return True

        return False

    def add_jersey_reading(self, number_str: str, score: float, timestamp: float):
        """Add a jersey number reading."""
        self.recent_readings.append({
            'number': number_str,
            'score': score,
            'timestamp': timestamp
        })

        # Update state based on reading
        current_time = time.time()

        if self.state == BindingState.PENDING and score >= self.lock_score_thr and number_str:
            # Transition to locked
            self.state = BindingState.LOCKED
            self.number_lock = number_str
            self.jersey_score = score
            self.state_changed_at = current_time
            logging.info(f"Track {self.track_id}: LOCKED with jersey '{number_str}' (score: {score:.3f})")
            return True  # Indicates state change to locked

        elif self.state == BindingState.LOCKED:
            # Update locked number if score is high enough
            if score >= self.lock_score_thr and number_str:
                if number_str != self.number_lock:
                    logging.info(f"Track {self.track_id}: Updated jersey '{self.number_lock}' -> '{number_str}'")
                self.number_lock = number_str
                self.jersey_score = score
                self.state_changed_at = current_time
            else:
                # Check if we should go stale
                if current_time - self.state_changed_at > self.stale_timeout_sec:
                    self.state = BindingState.STALE
                    logging.info(f"Track {self.track_id}: -> STALE")

        elif self.state == BindingState.STALE:
            # Can recover from stale with good reading
            if score >= self.lock_score_thr and number_str:
                self.state = BindingState.LOCKED
                self.number_lock = number_str
                self.jersey_score = score
                self.state_changed_at = current_time
                logging.info(f"Track {self.track_id}: STALE -> LOCKED with '{number_str}'")

        return False  # No state change to locked

    def get_current_jersey_info(self) -> Dict[str, Any]:
        """Get current jersey information."""
        if self.state in [BindingState.LOCKED, BindingState.STALE] and self.number_lock:
            return {
                "jersey_number": self.number_lock,
                "jersey_score": self.jersey_score,
                "binding_state": self.state.value,
                "backfilled": False
            }
        else:
            return {
                "jersey_number": "",
                "jersey_score": 0.0,
                "binding_state": self.state.value,
                "backfilled": False
            }


class SimpleJerseyEnricher:
    """
    Simplified Jersey Number Enricher
    Synchronous implementation for jersey number detection.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('jersey_detection', {}).get('enabled', False)

        if not self.enabled:
            logging.info("Jersey number detection is disabled")
            return

        # Initialize OCR model
        ocr_config = config.get('jersey_detection', {}).get('ocr', {})
        device = config.get('devices', 'cuda:0')
        if isinstance(device, list):
            device = device[0]

        weights_path = ocr_config.get('weights_path', 'jersey_ocr_best.pth')

        try:
            self.ocr_model = JerseyOCRModel(device=device, weights_path=weights_path)
        except Exception as e:
            logging.error(f"Failed to initialize OCR model: {e}")
            self.ocr_model = None

        # Track states
        track_config = config.get('jersey_detection', {}).get('tracking', {})
        self.track_states: Dict[int, SimpleTrackState] = {}
        self.track_config = track_config

        # OCR quality settings
        self.roi_min_area = ocr_config.get('roi_min_area', 400)
        self.roi_min_sharpness = ocr_config.get('roi_min_sharpness', 100.0)
        self.thr_len = ocr_config.get('thr_len', 0.6)
        self.thr_digit = ocr_config.get('thr_digit', 0.5)

        # Cleanup
        self.last_cleanup = time.time()
        self.cleanup_interval = 30.0  # seconds

        logging.info(f"SimpleJerseyEnricher initialized (enabled: {self.enabled})")

    def enrich_tracks(self, frame: np.ndarray, frame_id: int, timestamp: Union[str, float],
                      tracks: List[Dict], task_id: str) -> List[Dict]:
        """
        Main enrichment function - synchronous.
        
        Args:
            frame: Input frame image
            frame_id: Frame ID
            timestamp: Frame timestamp  
            tracks: List of tracking results
            task_id: Task ID
            
        Returns:
            List of enriched tracking results
        """
        # Add default fields if disabled
        if not self.enabled or self.ocr_model is None:
            for track in tracks:
                track.update({
                    "jersey_number": "",
                    "jersey_score": 0.0,
                    "binding_state": "pending",
                    "backfilled": False
                })
            return tracks

        current_time = time.time()
        parsed_timestamp = _parse_ts(timestamp)

        # Process each track
        for track in tracks:
            track_id = track["track_id"]

            # Create track state if needed
            if track_id not in self.track_states:
                self.track_states[track_id] = SimpleTrackState(track_id, self.track_config)
                logging.debug(f"Created track state for {track_id}")

            track_state = self.track_states[track_id]

            # Check if we should run OCR
            if track_state.should_trigger_ocr(frame_id, current_time):
                self._process_ocr(frame, track, track_state, parsed_timestamp)

            # Get current jersey info and add to track
            jersey_info = track_state.get_current_jersey_info()
            track.update(jersey_info)

        # Periodic cleanup
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup_tracks(current_time)
            self.last_cleanup = current_time

        return tracks

    def _process_ocr(self, frame: np.ndarray, track: Dict, track_state: SimpleTrackState, timestamp: float):
        """Process OCR for a track."""
        try:
            bbox = track["bbox"]

            # Extract ROI
            roi = extract_jersey_roi(frame, bbox)
            if roi is None:
                logging.debug(f"Track {track_state.track_id}: No valid ROI")
                return

            # Check quality
            if not check_roi_quality(roi, self.roi_min_area, self.roi_min_sharpness):
                logging.debug(f"Track {track_state.track_id}: ROI quality too low")
                return

            # Run OCR
            result = self.ocr_model.predict(roi, self.thr_len, self.thr_digit)

            # Add reading to track state
            locked = track_state.add_jersey_reading(
                result["number_str"],
                result["score"],
                timestamp
            )

            if result["number_str"]:
                logging.debug(f"Track {track_state.track_id}: OCR result '{result['number_str']}' "
                              f"(score: {result['score']:.3f}, locked: {locked})")

        except Exception as e:
            logging.error(f"OCR processing error for track {track_state.track_id}: {e}")

    def _cleanup_tracks(self, current_time: float):
        """Clean up old track states."""
        max_idle_time = 15.0  # seconds

        tracks_to_remove = []
        for track_id, track_state in self.track_states.items():
            time_since_change = current_time - track_state.state_changed_at
            if time_since_change > max_idle_time:
                tracks_to_remove.append(track_id)

        for track_id in tracks_to_remove:
            del self.track_states[track_id]
            logging.debug(f"Cleaned up track state {track_id}")

        if tracks_to_remove:
            logging.info(f"Cleaned up {len(tracks_to_remove)} track states")

    def get_stats(self) -> Dict[str, Any]:
        """Get enricher statistics."""
        if not self.enabled:
            return {"enabled": False}

        states = {}
        for track_id, track_state in self.track_states.items():
            states[track_id] = track_state.state.value

        return {
            "enabled": True,
            "active_tracks": len(self.track_states),
            "track_states": states
        }

    def shutdown(self):
        """Shutdown the enricher."""
        if hasattr(self, 'track_states'):
            self.track_states.clear()
        logging.info("SimpleJerseyEnricher shutdown")
