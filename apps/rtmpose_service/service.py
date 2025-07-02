# RTMPose Service Core Logic
# Handles Kafka I/O and pose estimation coordination

# TODO: Implement RTMPoseService class:
# - Kafka consumer setup for YOLOX detections
# - Kafka producer setup for pose keypoints
# - Multi-person pose estimation pipeline
# - Bounding box preprocessing and validation
# - Keypoint post-processing and filtering

# TODO: Integrate with core.models.rtmpose_model
# TODO: Add support for different pose models (17/133 keypoints)
# TODO: Implement efficient batch processing for multiple persons 
"""
RTMPose Service implementation for Kafka-based video processing pipeline.
Requires frame synchronization between raw frames and YOLOX detections.
"""
import asyncio
import logging
import json
import numpy as np
from typing import Dict, Any, Optional
import yaml
import os
import sys
from collections import defaultdict
import time

# Add parent directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from core.models.rtmpose_model import RTMPoseModel
from core.utils.kafka_io import KafkaMessageConsumer, KafkaMessageProducer
from core.utils.serializers import decode_image_message, encode_pose_message

logger = logging.getLogger(__name__)


class FrameSynchronizer:
    """Synchronizes raw frames with detection results."""

    def __init__(self, sync_timeout_ms: int = 5000):
        self.sync_timeout_ms = sync_timeout_ms
        self.frame_data = defaultdict(dict)  # task_id -> {frame_id -> {frame: ..., detections: ...}}
        self.last_cleanup = time.time()

    def add_frame(self, task_id: str, frame_id: int, frame_data: Dict):
        """Add raw frame data."""
        if task_id not in self.frame_data:
            self.frame_data[task_id] = {}

        if frame_id not in self.frame_data[task_id]:
            self.frame_data[task_id][frame_id] = {}

        self.frame_data[task_id][frame_id]['frame'] = frame_data
        self.frame_data[task_id][frame_id]['frame_timestamp'] = time.time()

    def add_detections(self, task_id: str, frame_id: int, detections_data: Dict):
        """Add detection results."""
        if task_id not in self.frame_data:
            self.frame_data[task_id] = {}

        if frame_id not in self.frame_data[task_id]:
            self.frame_data[task_id][frame_id] = {}

        self.frame_data[task_id][frame_id]['detections'] = detections_data
        self.frame_data[task_id][frame_id]['detections_timestamp'] = time.time()

    def get_synchronized_data(self, task_id: str, frame_id: int) -> Optional[Dict]:
        """Get synchronized frame and detection data."""
        if (task_id in self.frame_data and
                frame_id in self.frame_data[task_id] and
                'frame' in self.frame_data[task_id][frame_id] and
                'detections' in self.frame_data[task_id][frame_id]):

            data = self.frame_data[task_id][frame_id]

            # Check if data is not too old
            current_time = time.time()
            frame_age = (current_time - data.get('frame_timestamp', 0)) * 1000
            det_age = (current_time - data.get('detections_timestamp', 0)) * 1000

            if frame_age < self.sync_timeout_ms and det_age < self.sync_timeout_ms:
                # Clean up used data
                del self.frame_data[task_id][frame_id]
                return {
                    'frame': data['frame'],
                    'detections': data['detections']
                }

        return None

    def cleanup_old_data(self):
        """Clean up old unsynchronized data."""
        current_time = time.time()

        # Only cleanup every 10 seconds
        if current_time - self.last_cleanup < 10:
            return

        tasks_to_remove = []
        for task_id in self.frame_data:
            frames_to_remove = []

            for frame_id in self.frame_data[task_id]:
                frame_data = self.frame_data[task_id][frame_id]

                # Check if any timestamp is too old
                old_frame = False
                old_det = False

                if 'frame_timestamp' in frame_data:
                    frame_age = (current_time - frame_data['frame_timestamp']) * 1000
                    old_frame = frame_age > self.sync_timeout_ms

                if 'detections_timestamp' in frame_data:
                    det_age = (current_time - frame_data['detections_timestamp']) * 1000
                    old_det = det_age > self.sync_timeout_ms

                if old_frame or old_det:
                    frames_to_remove.append(frame_id)

            # Remove old frames
            for frame_id in frames_to_remove:
                del self.frame_data[task_id][frame_id]

            # Remove empty tasks
            if not self.frame_data[task_id]:
                tasks_to_remove.append(task_id)

        # Remove empty tasks
        for task_id in tasks_to_remove:
            del self.frame_data[task_id]

        self.last_cleanup = current_time


class RTMPoseService:
    """RTMPose pose estimation service with Kafka integration."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)

        # Initialize model
        model_config = self.config['model']
        self.model = RTMPoseModel(model_config)

        # Initialize Kafka components
        kafka_config = self.config['kafka']
        self.producer = KafkaMessageProducer(
            bootstrap_servers=kafka_config['bootstrap_servers']
        )

        # Frame synchronization
        sync_timeout = self.config['processing'].get('sync_timeout_ms', 5000)
        self.synchronizer = FrameSynchronizer(sync_timeout)

        # Consumer management
        self.consumers = {}
        self.active_tasks = set()

        logger.info("RTMPose Service initialized")
        logger.info(f"Model info: {self.model.get_model_info()}")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_file = os.path.join(os.path.dirname(__file__), config_path)

        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {config_file}: {e}")
            raise

    async def start_service(self):
        """Start the RTMPose service."""
        logger.info("Starting RTMPose service...")

        try:
            # Start cleanup task
            _ = asyncio.create_task(self._periodic_cleanup())

            # Start task discovery
            await self._discover_and_process_tasks()

        except KeyboardInterrupt:
            logger.info("Service interrupted by user")
        except Exception as e:
            logger.error(f"Service error: {e}")
            raise
        finally:
            await self._cleanup()

    async def _discover_and_process_tasks(self):
        """Discover new tasks and start processing them."""
        from kafka.admin import KafkaAdminClient
        from kafka.errors import KafkaError

        admin_client = KafkaAdminClient(
            bootstrap_servers=self.config['kafka']['bootstrap_servers']
        )

        while True:
            try:
                # List all topics
                topic_metadata = admin_client.list_topics()

                # Find yolox_* topics (our input)
                detection_topics = [
                    topic for topic in topic_metadata
                    if topic.startswith('yolox_')
                ]

                # Start processing new tasks
                for topic in detection_topics:
                    task_id = topic.replace('yolox_', '')

                    if task_id not in self.active_tasks:
                        logger.info(f"Discovered new task: {task_id}")
                        await self._start_task_processing(task_id)

                # Sleep before next discovery
                await asyncio.sleep(5)

            except KafkaError as e:
                logger.error(f"Kafka error during task discovery: {e}")
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Error during task discovery: {e}")
                await asyncio.sleep(10)

    async def _start_task_processing(self, task_id: str):
        """Start processing a specific task."""
        detection_topic = f"yolox_{task_id}"
        frame_topic = f"raw_frames_{task_id}"
        output_topic = f"rtmpose_{task_id}"

        try:
            # Create consumers for detections and frames
            detection_consumer = KafkaMessageConsumer(
                topics=[detection_topic],
                group_id=f"{self.config['kafka']['group_id']}_det_{task_id}",
                bootstrap_servers=self.config['kafka']['bootstrap_servers'],
                auto_offset_reset=self.config['kafka']['auto_offset_reset']
            )

            frame_consumer = KafkaMessageConsumer(
                topics=[frame_topic],
                group_id=f"{self.config['kafka']['group_id']}_frame_{task_id}",
                bootstrap_servers=self.config['kafka']['bootstrap_servers'],
                auto_offset_reset=self.config['kafka']['auto_offset_reset']
            )

            self.consumers[f"{task_id}_det"] = detection_consumer
            self.consumers[f"{task_id}_frame"] = frame_consumer
            self.active_tasks.add(task_id)

            logger.info(f"Started processing task {task_id}")

            # Start processing in background
            asyncio.create_task(
                self._process_detections(task_id, detection_consumer, output_topic)
            )
            asyncio.create_task(
                self._process_frames(task_id, frame_consumer)
            )

        except Exception as e:
            logger.error(f"Failed to start task processing for {task_id}: {e}")

    async def _process_detections(self, task_id: str, consumer: KafkaMessageConsumer, output_topic: str):
        """Process detection messages and synchronize with frames."""

        def process_detection_message(message: Dict):
            """Process a detection message."""
            try:
                frame_id = message['frame_id']

                # Add detections to synchronizer
                self.synchronizer.add_detections(task_id, frame_id, message)

                # Try to get synchronized data
                sync_data = self.synchronizer.get_synchronized_data(task_id, frame_id)

                if sync_data:
                    # Process synchronized frame + detections
                    self._process_synchronized_data(sync_data, output_topic)

            except Exception as e:
                logger.error(f"Error processing detection message for task {task_id}: {e}")

        def error_handler(error: Exception):
            """Handle processing errors."""
            logger.error(f"Detection consumer error for task {task_id}: {error}")

        # Start consuming detection messages
        try:
            consumer.consume_messages(process_detection_message, error_handler)
        except Exception as e:
            logger.error(f"Error in detection consumption for task {task_id}: {e}")

    async def _process_frames(self, task_id: str, consumer: KafkaMessageConsumer):
        """Process frame messages for synchronization."""

        def process_frame_message(message: Dict):
            """Process a frame message."""
            try:
                frame_id = message['frame_id']

                # Add frame to synchronizer
                self.synchronizer.add_frame(task_id, frame_id, message)

            except Exception as e:
                logger.error(f"Error processing frame message for task {task_id}: {e}")

        def error_handler(error: Exception):
            """Handle processing errors."""
            logger.error(f"Frame consumer error for task {task_id}: {error}")

        # Start consuming frame messages
        try:
            consumer.consume_messages(process_frame_message, error_handler)
        except Exception as e:
            logger.error(f"Error in frame consumption for task {task_id}: {e}")

    def _process_synchronized_data(self, sync_data: Dict, output_topic: str):
        """Process synchronized frame and detection data."""
        try:
            frame_data = sync_data['frame']
            detection_data = sync_data['detections']

            # Decode image from frame data
            image = decode_image_message(frame_data)

            # Prepare input for RTMPose model
            input_data = {
                'task_id': frame_data['task_id'],
                'frame_id': frame_data['frame_id'],
                'timestamp': frame_data['timestamp'],
                'image': image,
                'additional_data': {
                    'detections': detection_data.get('result', [])
                }
            }

            # Run RTMPose estimation
            result = self.model.predict(input_data)

            # Encode and send result
            pose_message = encode_pose_message(result)
            success = self.producer.send_message(output_topic, pose_message)

            if success:
                logger.debug(f"Processed pose estimation for frame {frame_data['frame_id']}")
            else:
                logger.error(f"Failed to send pose result for frame {frame_data['frame_id']}")

        except Exception as e:
            logger.error(f"Error processing synchronized data: {e}")

    async def _periodic_cleanup(self):
        """Periodically clean up old data."""
        while True:
            try:
                self.synchronizer.cleanup_old_data()
                await asyncio.sleep(10)  # Cleanup every 10 seconds
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                await asyncio.sleep(10)

    async def _cleanup(self):
        """Cleanup all resources."""
        logger.info("Cleaning up RTMPose service...")

        # Close all consumers
        for consumer in self.consumers.values():
            consumer.close()

        # Close producer
        self.producer.close()

        logger.info("RTMPose service cleanup complete")


async def main():
    """Main function to run the RTMPose service."""
    import argparse

    parser = argparse.ArgumentParser(description="RTMPose Estimation Service")
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Configuration file path')
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Create and start service
    service = RTMPoseService(args.config)
    await service.start_service()


if __name__ == "__main__":
    asyncio.run(main())