#!/usr/bin/env python3
"""
Test script for YOLOX model implementation.
"""
import numpy as np

import logging
import sys
import os

# Add path for imports
sys.path.insert(0, os.path.abspath('.'))

from core.models.yolox_model import YOLOXModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_yolox_model():
    """Test YOLOX model with a sample image."""

    # Model configuration
    config = {
        'model_path': 'https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip',
        'model_input_size': [640, 640],
        'confidence_threshold': 0.5,
        'nms_threshold': 0.45,
        'device': 'cpu',  # Use CPU for testing
        'backend': 'onnxruntime'
    }

    try:
        # Initialize model
        logger.info("Initializing YOLOX model...")
        model = YOLOXModel(config)
        logger.info("Model initialized successfully")

        # Print model info
        model_info = model.get_model_info()
        logger.info(f"Model info: {model_info}")

        # Create test image (640x480 random image)
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        # Prepare input data
        input_data = {
            'task_id': 'test_task_123',
            'frame_id': 1,
            'timestamp': '2025-01-20T10:00:00Z',
            'image': test_image
        }

        # Run prediction
        logger.info("Running prediction...")
        result = model.predict(input_data)

        logger.info(f"Prediction result: {result}")
        logger.info(f"Number of detections: {len(result.get('result', []))}")

        return True

    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    success = test_yolox_model()
    if success:
        logger.info("✅ YOLOX model test passed!")
    else:
        logger.error("❌ YOLOX model test failed!")
        sys.exit(1)