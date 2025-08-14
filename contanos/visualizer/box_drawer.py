"""
base on the kafka subscription interface, this class is used to draw boxes on the image frames.
frames data comes from raw_frames topic and the yolox topic.
yolox data structure is as follows:
 detection = {
                    "bbox": bbox,  # [x1, y1, x2, y2] format
                    "confidence": float(confidence),
                    "class_id": int(class_id),
                    "class_name": "person"  # YOLOX human art model focuses on person detection
                }
         result = {
                'detections': detections,
                'detection_count': len(detections),
                'model_info': {
                    'model_type': 'yolox',
                    'input_size': self.model_config.get('model_input_size', [640, 640]),
                    'confidence_threshold': conf_threshold
                },
                'processing_info': {
                    'worker_id': self.worker_id,
                    'device': self.device
                }
            }

raw_frame data structure is as follows:
return {
                'data': frame_np,
                'frame_id': str(payload_data.get('frame_id', record.offset)),
                'topic': record.topic,
                'partition': record.partition,
                'offset': record.offset,
                'timestamp': record.timestamp or time.time() * 1000,
                'payload': payload_data
            }

"""
from typing import Tuple

import cv2 as cv  # type: ignore
import numpy as np

TRACK_COLORS = [
    (0, 255, 255),  # Yellow
    (255, 0, 255),  # Magenta
    (255, 255, 0),  # Cyan
    (128, 0, 128),  # Purple
    (255, 165, 0),  # Orange
    (0, 128, 255),  # Light Blue
]


def get_track_color(track_id: int) -> Tuple[int, int, int]:
    """Get color for a specific track ID."""
    return TRACK_COLORS[track_id % len(TRACK_COLORS)]


def draw_boxes_on_frame(frame: np.ndarray,
                        detections: list,
                        scale: float = 1.0,
                        draw_labels: bool = True) -> np.ndarray:
    """
    Draw bounding boxes on the given frame.

    Args:
        frame (np.ndarray): The image frame to draw on.
        detections (list): List of detection dictionaries with 'bbox', 'track_id', 'score', and 'class_id'.
        scale (float): Scale factor for the bounding box coordinates.
        draw_labels (bool): Whether to draw labels on the boxes.

    Returns:
        np.ndarray: The annotated image frame.
    """
    if not isinstance(frame, np.ndarray):
        raise ValueError("Frame must be a numpy array")
    s_track_id = 1
    # detections=['bbox': [x1, y1, x2, y2], 'track_id': track_id, ]

    for detection in detections:
        bbox = detection.get('bbox', [])
        if len(bbox) < 4:
            continue
        x1, y1, x2, y2 = [int(coord * scale) for coord in bbox[:4]]
        track_id = detection.get('track_id', None)
        if not track_id:
            track_id = s_track_id
            s_track_id += 1
        # draw the bounding box
        cv.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
        color = get_track_color(track_id)
        speed_kmh = detection.get('speed_kmh', None)
        if speed_kmh is not None:
            label = f"ID: {track_id} {speed_kmh:.1f} km/h"
        else:
            label = f"ID: {track_id}"
        cv.putText(frame, label, (x1, y1 - 5), cv.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    return frame
