#!/usr/bin/env python3
"""
Test script for KafkaController topic creation.
"""
import sys
import os
import logging
import uuid

# Add apps directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "apps")))

from fastapi_backend.kafka_controller import KafkaController

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_topic_creation():
    """Test topic creation and listing."""
    logger.info("🧪 Testing KafkaController topic creation")
    
    # Generate test task ID
    test_task_id = str(uuid.uuid4())
    logger.info(f"Test task ID: {test_task_id}")
    
    try:
        # Initialize controller
        kafka_controller = KafkaController()
        
        # Test topic creation
        logger.info("Creating topics...")
        success = kafka_controller.create_topics_for_task(test_task_id)
        
        if success:
            logger.info("✅ Topics created successfully!")
            
            # List topics for verification
            logger.info("Listing topics for task...")
            topics = kafka_controller.list_topics_for_task(test_task_id)
            logger.info(f"Found topics: {topics}")
            
            expected_topics = [
                f"raw_frames_{test_task_id}",
                f"yolox_detections_{test_task_id}",
                f"rtmpose_results_{test_task_id}",
                f"bytetrack_tracking_{test_task_id}",
                f"outstream_{test_task_id}"
            ]
            
            missing_topics = [topic for topic in expected_topics if topic not in topics]
            if missing_topics:
                logger.error(f"❌ Missing topics: {missing_topics}")
                return False
            else:
                logger.info("✅ All expected topics found!")
                
                # Clean up test topics immediately
                logger.info("Cleaning up test topics...")
                kafka_controller.delete_topics_for_task(test_task_id, delay_seconds=0)
                return True
        else:
            logger.error("❌ Failed to create topics")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False
    finally:
        if 'kafka_controller' in locals():
            kafka_controller.close()

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Kafka Topic Creation Test")
    print("=" * 60)
    
    success = test_topic_creation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Topic creation test passed!")
    else:
        print("💥 Topic creation test failed!")
    print("=" * 60)
    
    sys.exit(0 if success else 1) 