#!/usr/bin/env python3
"""
YOLOX Detection Worker using contanos framework.
"""
import logging
from typing import Dict, Optional

from apps.yolox_service.MultiGPUYolo import MultiGPUYOLOX as YOLOX
from contanos import deserialize_image_from_kafka
from contanos.base_worker import BaseWorker


# from rtmlib import YOLOX


class YOLOXWorker(BaseWorker):
    """YOLOX detection worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        super().__init__(worker_id, device, model_config,
                         input_interface, output_interface)

        logging.info(f"YOLOXWorker {worker_id} initialized on device {device}")

    def _model_init(self):
        """Initialize the YOLOX model."""
        try:
            # Create model configuration
            device = self.device
            # if self.device.startswith('cuda'):
            #     device = 'cuda'
            model_config = self.model_config
            # Handle different model configuration formats
            self.model = YOLOX(**model_config, device=device)
            logging.info(f"YOLOXWorker {self.worker_id} model initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize YOLOX model for worker {self.worker_id}: {e}")
            raise

    def _predict(self, inputs: Dict) -> Optional[Dict]:
        """Run YOLOX detection on input frame."""
        try:
            frame = inputs.get('image_bytes')
            if frame is None:
                logging.error(f"Worker {self.worker_id} received empty input frame")
                return None

            deserializer_frame = deserialize_image_from_kafka(frame)
            # Run model inference

            model_output = self.model(deserializer_frame)
            # output :[[  1.7640184   2.6469145 212.87782   337.55084  ]]
            if model_output is None or len(model_output) == 0:
                logging.warning(f"Worker {self.worker_id} received empty model output")
                return None
            # Convert model output to detection format
            detections = []
            for bbox in model_output:
                if hasattr(bbox, 'tolist'):
                    bbox = bbox.tolist()
                if len(bbox) < 4:
                    logging.warning(f"Worker {self.worker_id} received invalid bounding box: {bbox}")
                    continue
                x1, y1, x2, y2 = bbox[:4]
                detections.append({"bbox": [x1, y1, x2, y2],
                                   'score': bbox[4] if len(bbox) > 4 else 1.0, })

            result = {
                'detections': detections,
                'detection_count': len(detections),
                'frame_id': inputs.get('frame_id', None),
                'timestamp': inputs.get('timestamp', None),

            }
            return result

        except Exception as e:
            logging.error(f"Worker {self.worker_id} prediction error: {e}")
            return None
