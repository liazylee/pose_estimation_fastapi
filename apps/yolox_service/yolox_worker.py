#!/usr/bin/env python3
"""
YOLOX Detection Worker using contanos framework.
"""
import logging
from typing import Any, Dict

import numpy as np
from rtmlib.tools.object_detection import YOLOX as YOLOXModel

from contanos.base_worker import BaseWorker


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
            model_kwargs = {
                'device': self.device,
                **self.model_config
            }

            # Handle different model configuration formats
            if 'model_path' in self.model_config:
                model_kwargs['model_path'] = self.model_config['model_path']
            elif 'onnx_model' in self.model_config:
                model_kwargs['onnx_model'] = self.model_config['onnx_model']

            self.model = YOLOXModel(**model_kwargs)
            logging.info(f"YOLOXWorker {self.worker_id} model initialized successfully")

        except Exception as e:
            logging.error(f"Failed to initialize YOLOX model for worker {self.worker_id}: {e}")
            raise

    def _predict(self, inputs: Any, metadata: Any = None) -> Any:
        """Run YOLOX detection on input frame."""
        try:
            # Ensure input is numpy array
            if not isinstance(inputs, np.ndarray):
                logging.error(f"Worker {self.worker_id}: Expected numpy array, got {type(inputs)}")
                return None

            # Run model inference
            model_output = self.model(inputs)

            # Handle different output formats
            if isinstance(model_output, tuple):
                bboxes, det_scores = model_output
                classes = [-1] * len(det_scores)  # Default class for all detections
            elif isinstance(model_output, dict):
                bboxes = model_output.get('bboxes', [])
                det_scores = model_output.get('scores', [])
                classes = model_output.get('classes', [-1] * len(det_scores))
            else:
                # Model returns only bboxes
                bboxes = model_output
                det_scores = np.ones(len(bboxes)) if len(bboxes) > 0 else []
                classes = [-1] * len(det_scores)

            # Apply confidence threshold if configured
            conf_threshold = self.model_config.get('confidence_threshold', 0.5)  # Lower threshold for testing
            if conf_threshold > 0 and len(det_scores) > 0:
                valid_indices = np.array(det_scores) >= conf_threshold
                bboxes = np.array(bboxes)[valid_indices] if len(bboxes) > 0 else []
                det_scores = np.array(det_scores)[valid_indices]
                classes = np.array(classes)[valid_indices]

            # Convert to lists for JSON serialization
            if isinstance(bboxes, np.ndarray):
                bboxes = bboxes.tolist()
            if isinstance(det_scores, np.ndarray):
                det_scores = det_scores.tolist()
            if isinstance(classes, np.ndarray):
                classes = classes.tolist()

            # Format detections according to system message schema
            detections = []
            for i in range(len(det_scores)):
                bbox = bboxes[i] if i < len(bboxes) else [0, 0, 0, 0]
                confidence = det_scores[i] if i < len(det_scores) else 0.0
                class_id = classes[i] if i < len(classes) else -1

                detection = {
                    "bbox": bbox,  # [x1, y1, x2, y2] format
                    "confidence": float(confidence),
                    "class_id": int(class_id),
                    "class_name": "person"  # YOLOX human art model focuses on person detection
                }
                detections.append(detection)

            # Create result in the expected format
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
            logging.info(f"YOLOXWorker {self.worker_id} detection result: {len(result)}")
            logging.info(
                f"Worker {self.worker_id} detected {len(detections)} objects with confidence >= {conf_threshold}")
            return result

        except Exception as e:
            logging.error(f"Worker {self.worker_id} prediction error: {e}")
            return None
