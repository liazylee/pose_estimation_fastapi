#!/usr/bin/env python3
"""
Test script for RTMPose model implementation.
"""
import numpy as np
import cv2
import logging
import sys
import os

# Add path for imports
sys.path.insert(0, os.path.abspath('.'))

from core.models.rtmpose_model import RTMPoseModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rtmpose_model():
    """Test RTMPose model with sample detections."""
    
    # Model configuration
    config = {
        'model_path': 'https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.zip',
        'model_input_size': [192, 256],
        'keypoint_threshold': 0.3,
        'device': 'cpu',  # Use CPU for testing
        'backend': 'onnxruntime',
        'num_keypoints': 17
    }
    
    try:
        # Initialize model
        logger.info("Initializing RTMPose model...")
        model = RTMPoseModel(config)
        logger.info("Model initialized successfully")
        
        # Print model info
        model_info = model.get_model_info()
        logger.info(f"Model info: {model_info}")
        
        # Create test image (640x480 random image)
        test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        # Mock detection results from YOLOX
        mock_detections = [
            {
                "person_id": 0,
                "bbox": [100, 50, 200, 300],  # [x, y, width, height]
                "confidence": 0.85
            },
            {
                "person_id": 1,
                "bbox": [350, 80, 180, 280],
                "confidence": 0.92
            }
        ]
        
        # Prepare input data
        input_data = {
            'task_id': 'test_task_123',
            'frame_id': 1,
            'timestamp': '2025-01-20T10:00:00Z',
            'image': test_image,
            'additional_data': {
                'detections': mock_detections
            }
        }
        
        # Run prediction
        logger.info("Running pose estimation...")
        result = model.predict(input_data)
        
        logger.info(f"Pose estimation result: {result}")
        logger.info(f"Number of poses: {len(result.get('result', []))}")
        
        # Print keypoint details
        for i, pose in enumerate(result.get('result', [])):
            logger.info(f"Person {i}:")
            logger.info(f"  - BBox: {pose['bbox']}")
            logger.info(f"  - Keypoints: {len(pose['keypoints'])}")
            logger.info(f"  - Detection confidence: {pose.get('detection_confidence', 'N/A')}")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_rtmpose_model()
    if success:
        logger.info("✅ RTMPose model test passed!")
    else:
        logger.error("❌ RTMPose model test failed!")
        sys.exit(1) 