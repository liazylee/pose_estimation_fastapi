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
import cv2 as cv  # type: ignore
import numpy as np


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
    for detection in detections:

        if len(detection) < 4:
            continue  # Skip invalid bounding boxes

        x1, y1, x2, y2 = [int(coord * scale) for coord in detection]

        # Draw rectangle
        cv.rectangle(frame, (x1, y1), (x2, y2), color=(0, 255, 0), thickness=1)
        track_id = None
        # todo :  get real track_id from detection later
        if draw_labels:
            # Create label with available information
            if track_id is not None:
                label = f"ID: {track_id}"
            else:
                # If no track_id, show confidence and class name
                label = f"ID: {s_track_id}"
                s_track_id += 1
            cv.putText(frame, label, (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame
