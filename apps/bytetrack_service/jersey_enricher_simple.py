#!/usr/bin/env python3
"""
Simplified Jersey Number Enricher
Synchronous implementation without async complexity.
"""

import logging
import time
from collections import deque
from enum import Enum
from typing import Dict, List, Optional, Union

import numpy as np

from .helper import _parse_ts
from .jersey_ocr import JerseyOCRModel, extract_jersey_roi, check_roi_quality


class BindingState(Enum):
    """Track binding states for jersey numbers."""
    PENDING = "pending"
    LOCKED = "locked"
    STALE = "stale"


class SimpleTrackState:
    def __init__(self, track_id: int, config: Dict):
        self.track_id = track_id
        self.config = config
        self.state = BindingState.PENDING
        self.state_changed_at = time.time()
        self.number_lock: Optional[str] = None
        self.jersey_score = 0.0
        self.last_ocr_time = 0.0
        self.last_ocr_frame = 0
        self.ocr_interval_frames = config.get('ocr_interval_frames', 15)
        self.ocr_interval_sec = config.get('ocr_interval_sec', 0.5)
        self.lock_score_thr = config.get('lock_score_thr', 0.7)
        self.stale_timeout_sec = config.get('stale_timeout_sec', 8.0)
        self.recent_readings = deque(maxlen=5)

    def should_trigger_ocr(self, frame_id: int, now: float) -> bool:
        return (frame_id - self.last_ocr_frame >= self.ocr_interval_frames or
                now - self.last_ocr_time >= self.ocr_interval_sec)

    def add_reading(self, number_str, score, ts):
        self.recent_readings.append({"number": number_str, "score": score, "timestamp": ts})
        now = time.time()
        if self.state == BindingState.PENDING and score >= self.lock_score_thr and number_str:
            self.state = BindingState.LOCKED
            self.number_lock = number_str
            self.jersey_score = score
            self.state_changed_at = now
            return True
        elif self.state == BindingState.LOCKED:
            if score >= self.lock_score_thr and number_str:
                self.number_lock = number_str
                self.jersey_score = score
                self.state_changed_at = now
            elif now - self.state_changed_at > self.stale_timeout_sec:
                self.state = BindingState.STALE
        elif self.state == BindingState.STALE:
            if score >= self.lock_score_thr and number_str:
                self.state = BindingState.LOCKED
                self.number_lock = number_str
                self.jersey_score = score
                self.state_changed_at = now
        return False

    def current_info(self):
        if self.state in [BindingState.LOCKED, BindingState.STALE] and self.number_lock:
            return {"jersey_number": self.number_lock, "jersey_score": self.jersey_score,
                    "binding_state": self.state.value, "backfilled": False}
        return {"jersey_number": "", "jersey_score": 0.0,
                "binding_state": self.state.value, "backfilled": False}


class SimpleJerseyEnricher:
    def __init__(self, config: Dict):
        self.config = config
        self.enabled = config.get('jersey_detection', {}).get('enabled', False)
        if not self.enabled:
            logging.info("Jersey detection disabled")
            return

        ocr_cfg = config.get('jersey_detection', {}).get('ocr', {})
        backbone = ocr_cfg.get('backbone', 'mobilenet_v3')
        device = config.get('devices', 'cuda:0')
        if isinstance(device, list): device = device[0]
        weights = ocr_cfg.get('weights_path', 'jersey_ocr_best.pth')

        try:
            self.ocr_model = JerseyOCRModel(backbone=backbone, device=device, weights_path=weights)
        except Exception as e:
            logging.error(f"OCR init failed: {e}")
            self.ocr_model = None

        self.track_states: Dict[int, SimpleTrackState] = {}
        self.roi_min_area = ocr_cfg.get('roi_min_area', 400)
        self.roi_min_sharpness = ocr_cfg.get('roi_min_sharpness', 100.0)
        self.thr_len = ocr_cfg.get('thr_len', 0.6)
        self.thr_digit = ocr_cfg.get('thr_digit', 0.5)
        self.last_cleanup = time.time()
        self.cleanup_interval = 30.0

    def enrich_tracks(self,
                      frame: np.ndarray,
                      frame_id: int,
                      timestamp: Union[str, float],  # 与调用方一致
                      tracks: List[Dict],
                      task_id: str):
        if not self.enabled or self.ocr_model is None:
            for t in tracks:
                t.update({"jersey_number": "", "jersey_score": 0.0,
                          "binding_state": "pending", "backfilled": False})
            return tracks

        now = time.time()
        # ✅ 解析 timestamp，兼容 iso 字符串/float
        parsed_ts = _parse_ts(timestamp)
        if parsed_ts is None:
            parsed_ts = now

        for track in tracks:
            tid = track["track_id"]
            if tid not in self.track_states:
                self.track_states[tid] = SimpleTrackState(tid, self.config)
            st = self.track_states[tid]

            if st.should_trigger_ocr(frame_id, now):
                self._process_ocr(frame, track, st, parsed_ts)
                st.last_ocr_frame, st.last_ocr_time = frame_id, now

            track.update(st.current_info())

        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup(now)
        return tracks

    def _process_ocr(self, frame, track, st, ts):
        try:
            roi = extract_jersey_roi(frame, track["bbox"])
            if roi is None or not check_roi_quality(roi, self.roi_min_area, self.roi_min_sharpness):
                return
            res = self.ocr_model.predict(roi, self.thr_len, self.thr_digit)
            st.add_reading(res["number_str"], res["score"], ts)
        except Exception as e:
            logging.error(f"OCR error: {e}")

    def _cleanup(self, now):
        to_remove = [tid for tid, st in self.track_states.items()
                     if now - st.state_changed_at > 15]
        for tid in to_remove: self.track_states.pop(tid, None)
        self.last_cleanup = now

    def shutdown(self):
        """Shutdown the enricher."""
        if hasattr(self, 'track_states'):
            self.track_states.clear()
        logging.info("SimpleJerseyEnricher shutdown")
