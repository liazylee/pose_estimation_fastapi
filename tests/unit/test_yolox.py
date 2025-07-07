#!/usr/bin/env python3
"""
Unit tests for YOLOX model.
"""
import unittest
import sys
import os
import numpy as np

# Add paths for testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.models.yolox_model import YOLOXModel


class TestYOLOXModel(unittest.TestCase):
    """Test YOLOX model functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'device': 'cpu',
            'model_path': 'test_model.onnx',
            'backend': 'onnxruntime'
        }

    def test_model_initialization(self):
        """Test model initialization."""
        try:
            model = YOLOXModel(self.config)
            self.assertIsNotNone(model)
            self.assertEqual(model.device, 'cpu')
        except ImportError:
            # Skip test if rtmlib not available
            self.skipTest("rtmlib not available")

    def test_model_info(self):
        """Test model info retrieval."""
        try:
            model = YOLOXModel(self.config)
            info = model.get_model_info()
            self.assertIn('model_type', info)
            self.assertEqual(info['model_type'], 'YOLOX')
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