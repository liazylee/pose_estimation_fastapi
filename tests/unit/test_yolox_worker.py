"""

test for YOLOXWorker using contanos framework.
               message= {
          "task_id": "mytask123",
          "frame_id": 12,
          "timestamp": "2025-07-05T17:30:21.874000Z",
          "source_id": "myvideo.mp4",
          "image_format": "jpeg",
          "image_bytes": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDA...",  // base64 data (truncated)
          "metadata": {
            "original_width": 1920,
            "original_height": 1080,
            "scale_factor": 1.0,
            "fps": 29.97
          }
    }
"""
import logging

import cv2

from apps.yolox_service.yolox_worker import YOLOXWorker
from contanos import serialize_image_for_kafka

kafka_message = {
    "task_id": "mytask123",
    "frame_id": 12,
    "timestamp": "2025-07-05T17:30:21.874000Z",
    "source_id": "myvideo.mp4",
    "image_format": "jpeg",
    "image_bytes": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDA...",
    "metadata": {
        "original_width": 1920,
        "original_height": 1080,
        "scale_factor": 1.0,
        "fps": 29.97
    }
}

img_path = 'human-pose.jpeg'
img = cv2.imread(img_path)
img = serialize_image_for_kafka(img, use_base64=True, quality=90)
assert img is not None
kafka_message['image_bytes'] = img
# --- Prepare YOLOXWorker ---
yolox_config = {
    "model_input_size": [640, 640],
    "onnx_model": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip",
    "device": "cuda",
    "backend": "onnxruntime"
}
logging.basicConfig(level=logging.INFO)
dummy_interface = None

worker = YOLOXWorker(
    worker_id=0,
    device='cuda',  # or 'cpu'
    model_config=yolox_config,
    input_interface=dummy_interface,
    output_interface=dummy_interface
)

worker._model_init()
# --- Run prediction ---
result = worker._predict(kafka_message)

print(result)
