#!/usr/bin/env python3
"""
Unit tests for YOLOX model.
"""
import os
import sys
import unittest

import cv2
import numpy as np

from apps.yolox_service.yolox_worker import YOLOXWorker as YOLOXModel
from contanos import serialize_image_for_kafka

# Add paths for testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


class TestYOLOXModel(unittest.TestCase):
    """Test YOLOX model functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "onnx_model": "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip",
            'backend': 'onnxruntime'
        }

    def test_model_initialization(self):
        """Test model initialization."""
        try:
            model = YOLOXModel(worker_id=0, device='cuda', model_config=self.config,
                               input_interface=None, output_interface=None, )
            self.assertIsNotNone(model)
            # self.assertIsNotNone(model)
            # self.assertEqual(model.device, 'cpu')
        except ImportError:
            # Skip test if rtmlib not available
            self.skipTest("rtmlib not available")

    # cv read a image from a file human-pose.jpeg

    def test_model_inference(self):
        """Test model inference."""
        try:
            model = YOLOXModel(worker_id=0, device='cuda', model_config=self.config,
                               input_interface=None, output_interface=None, )

            # Create dummy input
            image = cv2.imread('human-pose.jpeg')
            base64_image = serialize_image_for_kafka(image,
                                                    
                                                     quality=90)
            input_data = {
                'task_id': 'test_task',
                'frame_id': 1,
                'timestamp': '2024-01-01T00:00:00Z',
                'image_bytes': base64_image
            }

            result = model._predict(input_data)
            print(result)
            # Check if result is a dictionary
            self.assertIsInstance(result, dict)
            self.assertIn('detections', result)
            self.assertIn('detection_count', result)

        except ImportError:
            self.skipTest("rtmlib not available")

    def test_predict_format(self):
        """Test prediction output format."""
        try:
            model = YOLOXModel(self.config)

            # Create dummy input
            input_data = {
                'task_id': 'test_task',
                'frame_id': 1,
                'timestamp': '2024-01-01T00:00:00Z',
                'image': np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            }

            result = model.predict(input_data)

            # Check result format
            self.assertIn('task_id', result)
            self.assertIn('frame_id', result)
            self.assertIn('timestamp', result)
            self.assertIn('result', result)

        except ImportError:
            self.skipTest("rtmlib not available")


if __name__ == '__main__':
    unittest.main()
