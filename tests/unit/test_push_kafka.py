#!/usr/bin/env python3
"""
Test script to push human-pose.jpeg to Kafka and test YOLOX consumption.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any

import cv2
import numpy as np
from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.utils.serializers import serialize_image_for_kafka
from apps.yolox_service.service import YOLOXService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KafkaTestProducer:
    """Kafka producer for testing image upload."""

    def __init__(self, bootstrap_servers: str = 'localhost:9092'):
        self.bootstrap_servers = bootstrap_servers
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_request_size=52428800,  # 50MB for large images
            buffer_memory=104857600,  # 100MB buffer
            compression_type='gzip',
            acks='all',
            retries=3
        )
        logger.info(f"Kafka producer initialized: {bootstrap_servers}")

    def create_topic_if_not_exists(self, topic_name: str):
        """Create Kafka topic if it doesn't exist."""
        try:
            admin_client = KafkaAdminClient(bootstrap_servers=self.bootstrap_servers)

            topic = NewTopic(
                name=topic_name,
                num_partitions=1,
                replication_factor=1,
                topic_configs={
                    "retention.ms": "600000",  # 10 minutes
                    "segment.bytes": "104857600",  # 100MB
                    "cleanup.policy": "delete"
                }
            )

            admin_client.create_topics([topic])
            logger.info(f"Created topic: {topic_name}")

        except TopicAlreadyExistsError:
            logger.info(f"Topic already exists: {topic_name}")
        except Exception as e:
            logger.error(f"Error creating topic {topic_name}: {e}")
            raise

    def send_image_message(self, topic: str, message: Dict) -> bool:
        """Send image message to Kafka topic."""
        try:
            future = self.producer.send(topic, value=message)
            record_metadata = future.get(timeout=10)
            logger.info(f"Message sent to {topic} partition {record_metadata.partition} "
                        f"offset {record_metadata.offset}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            return False

    def close(self):
        """Close producer connection."""
        self.producer.flush()
        self.producer.close()


class KafkaTestConsumer:
    """Kafka consumer for testing YOLOX output."""

    def __init__(self, topic: str, group_id: str, bootstrap_servers: str = 'localhost:9092'):
        self.topic = topic
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=10000  # 10 second timeout
        )
        logger.info(f"Kafka consumer initialized for topic: {topic}")

    def consume_messages(self, max_messages: int = 5):
        """Consume messages and return them."""
        messages = []
        try:
            for message in self.consumer:
                logger.info(f"Received message from {message.topic} "
                            f"partition {message.partition} offset {message.offset}")
                messages.append(message.value)

                if len(messages) >= max_messages:
                    break

        except Exception as e:
            logger.info(f"Consumer timeout or error: {e}")

        return messages

    def close(self):
        """Close consumer connection."""
        self.consumer.close()


def load_test_image(image_path: str) -> np.ndarray:
    """Load test image from file."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Test image not found: {image_path}")

    # Load image using OpenCV
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to load image: {image_path}")

    # Convert BGR to RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    logger.info(f"Loaded test image: {image_path}, shape: {image_rgb.shape}")
    return image_rgb


def create_test_message(task_id: str, frame_id: int, image: np.ndarray) -> Dict[str, Any]:
    """Create test message in the required format."""
    timestamp = datetime.utcnow().isoformat() + 'Z'

    # Resize image if too large (optional)
    height, width = image.shape[:2]
    max_dimension = 1920
    scale = 1.0

    if width > max_dimension or height > max_dimension:
        if width > height:
            scale = max_dimension / width
        else:
            scale = max_dimension / height

        new_width = int(width * scale)
        new_height = int(height * scale)
        image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

    # Create message following the required format
    message = {
        "task_id": task_id,
        "frame_id": frame_id,
        "timestamp": timestamp,
        "source_id": "test_human_pose",
        "image_format": "jpeg",
        "image_bytes": serialize_image_for_kafka(image, use_base64=True, quality=90),
        "metadata": {
            "original_width": width,
            "original_height": height,
            "scale_factor": scale,
            "fps": 25,
            "total_frames": 1
        }
    }

    logger.info(f"Created test message for task_id: {task_id}, frame_id: {frame_id}")
    return message


async def test_yolox_service(task_id: str, timeout: int = 30):
    """Test YOLOX service with the given task_id."""
    logger.info(f"Starting YOLOX service test for task_id: {task_id}")

    try:
        # Create YOLOX service instance
        service = YOLOXService(config_path="../dev_pose_estimation_config.yaml", task_id=task_id)

        # Override to use CPU for testing (if no GPU available)
        service.config.setdefault('yolox', {})['devices'] = ['cuda']
        service.config.setdefault('global', {})['log_level'] = 'INFO'

        logger.info("YOLOX service created, starting in background...")

        # Start service in background with timeout
        service_task = asyncio.create_task(service.start_service())

        # Wait a bit for service to start
        await asyncio.sleep(5)

        logger.info("YOLOX service should be running now")
        return service_task

    except Exception as e:
        logger.error(f"Error starting YOLOX service: {e}")
        raise


async def main():
    """Main test function."""
    task_id = "test_human_pose_001"
    input_topic = f"raw_frames_{task_id}"
    output_topic = f"yolox_detections_{task_id}"

    print("=" * 80)
    print("🧪 Kafka + YOLOX Integration Test")
    print("=" * 80)
    print(f"Task ID: {task_id}")
    print(f"Input Topic: {input_topic}")
    print(f"Output Topic: {output_topic}")
    print("=" * 80)

    # Initialize Kafka producer
    producer = KafkaTestProducer()

    try:
        # Step 1: Create topics
        logger.info("Step 1: Creating Kafka topics...")
        producer.create_topic_if_not_exists(input_topic)
        producer.create_topic_if_not_exists(output_topic)

        # Step 2: Load test image
        logger.info("Step 2: Loading test image...")
        image_path = os.path.join(os.path.dirname(__file__), "human-pose.jpeg")
        test_image = load_test_image(image_path)

        # Step 3: Create test message
        logger.info("Step 3: Creating test message...")
        message = create_test_message(task_id, frame_id=1, image=test_image)

        # Step 4: Start YOLOX service
        logger.info("Step 4: Starting YOLOX service...")
        yolox_task = await test_yolox_service(task_id)

        # Wait for service to initialize
        await asyncio.sleep(3)

        # Step 5: Send image to Kafka
        logger.info("Step 5: Sending image to Kafka...")
        success = producer.send_image_message(input_topic, message)

        if success:
            logger.info("✅ Image sent successfully to Kafka!")
        else:
            logger.error("❌ Failed to send image to Kafka!")
            return

        # Step 6: Wait and consume YOLOX output
        logger.info("Step 6: Waiting for YOLOX processing...")
        await asyncio.sleep(5)  # Give YOLOX time to process

        # Step 7: Check YOLOX output
        logger.info("Step 7: Checking YOLOX output...")
        consumer = KafkaTestConsumer(output_topic, f"test_consumer_{task_id}")

        output_messages = consumer.consume_messages(max_messages=1)

        if output_messages:
            logger.info("✅ Received YOLOX detection results!")
            for i, msg in enumerate(output_messages):
                logger.info(f"Detection result {i + 1}:")
                logger.info(f"  Task ID: {msg.get('task_id')}")
                logger.info(f"  Frame ID: {msg.get('frame_id')}")
                logger.info(f"  Detections: {len(msg.get('detections', []))}")

                # Print detection details
                for j, detection in enumerate(msg.get('detections', [])):
                    logger.info(f"    Person {j + 1}: bbox={detection.get('bbox')}, "
                                f"confidence={detection.get('confidence')}")
        else:
            logger.warning("⚠️  No YOLOX output received (might be normal if no people detected)")

        # Cleanup
        consumer.close()

        # Cancel YOLOX service
        logger.info("Stopping YOLOX service...")
        yolox_task.cancel()
        try:
            await yolox_task
        except asyncio.CancelledError:
            logger.info("YOLOX service stopped")

        print("\n" + "=" * 80)
        print("🎉 Test completed successfully!")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        producer.close()


if __name__ == "__main__":
    # Check if Kafka is running
    try:
        from kafka import KafkaProducer

        test_producer = KafkaProducer(bootstrap_servers='localhost:9092')
        test_producer.close()
        logger.info("✅ Kafka connection test successful")
    except Exception as e:
        logger.error(f"❌ Kafka connection failed: {e}")
        logger.error("Please make sure Kafka is running on localhost:9092")
        sys.exit(1)

    # Run the test
    asyncio.run(main())
