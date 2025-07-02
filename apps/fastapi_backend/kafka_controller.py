# Kafka Topic Lifecycle Management
# Handles dynamic creation and deletion of task-specific Kafka topics

# TODO: Implement the following functions:
# - create_kafka_topics(task_id): Create all required topics for a task
# - delete_kafka_topics(task_id): Clean up topics after task completion
# - get_kafka_admin_client(): Get configured Kafka admin client
# - validate_topics_exist(task_id): Check if topics are properly created

# Topics to manage per task:
# - raw_frames_{task_id}
# - yolox_{task_id} 
# - rtmpose_{task_id}
# - bytetrack_{task_id}

# TODO: Configure topic settings (retention, partitions, etc.) 
"""
Kafka controller for managing topics and messaging.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

logger = logging.getLogger(__name__)


class KafkaController:
    """Manages Kafka operations for the video processing pipeline."""

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.admin_client = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._init_admin_client()

    def _init_admin_client(self):
        """Initialize Kafka admin client with retry logic."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.admin_client = KafkaAdminClient(
                    bootstrap_servers=self.bootstrap_servers,
                    client_id='video_pipeline_admin'
                )
                logger.info("Kafka admin client initialized successfully")
                return
            except Exception as e:
                logger.warning(f"Failed to connect to Kafka (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("Failed to initialize Kafka admin client")
                    raise

    def create_topics_for_task(self, task_id: str) -> bool:
        """
        Create all required Kafka topics for a video processing task.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            True if successful, False otherwise
        """
        topic_configs = {
            "retention.ms": "600000",  # 10 minutes
            "segment.bytes": "104857600",  # 100MB
            "cleanup.policy": "delete",
            "compression.type": "snappy",  # Efficient for JSON
            "max.message.bytes": "52428800"  # 50MB for large frames
        }

        # Create topics matching the configuration file naming convention
        topic_names = [
            f"raw_frames_{task_id}",  # Input frames
            f"yolox_detections_{task_id}",  # YOLOX detection results
            f"rtmpose_results_{task_id}",  # RTMPose pose estimation results
            f"bytetrack_tracking_{task_id}",  # ByteTrack tracking results
            f"outstream_{task_id}"  # Output stream topic (if needed)
        ]

        topics = [
            NewTopic(
                name=topic_name,
                num_partitions=1,
                replication_factor=1,
                topic_configs=topic_configs
            )
            for topic_name in topic_names
        ]

        try:
            # Create topics
            self.admin_client.create_topics(new_topics=topics, validate_only=False, timeout_ms=30000)
            logger.info(f"Created topics for task {task_id}: {topic_names}")
            return True

        except TopicAlreadyExistsError as e:
            logger.warning(f"Some topics already exist for task {task_id}: {e}")
            return True  # Not a fatal error

        except Exception as e:
            logger.error(f"Failed to create topics for task {task_id}: {e}")
            return False

    def delete_topics_for_task(self, task_id: str, delay_seconds: int = 60 * 60 * 2):
        """
        Delete all Kafka topics for a task after a delay.
        """

        def _delete_with_delay():
            if delay_seconds > 0:
                logger.info(f"Scheduling topic deletion for task {task_id} in {delay_seconds} seconds")
                time.sleep(delay_seconds)

            # Match the same topic names created in create_topics_for_task
            topics = [
                f"raw_frames_{task_id}",
                f"yolox_detections_{task_id}",
                f"rtmpose_results_{task_id}",
                f"bytetrack_tracking_{task_id}",
                f"outstream_{task_id}"
            ]

            try:
                self.admin_client.delete_topics(topics=topics, timeout_ms=30000)
                logger.info(f"Deleted topics: {topics}")
            except Exception as e:
                logger.error(f"Failed to delete topics for task {task_id}: {e}")

        self.executor.submit(_delete_with_delay)

    def list_topics_for_task(self, task_id: str) -> list:
        """List all topics for a specific task."""
        try:
            all_topics = self.admin_client.list_topics()
            task_topics = [topic for topic in all_topics if topic.endswith(f"_{task_id}")]
            return task_topics
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            return []

    def close(self):
        """Close connections and cleanup resources."""
        if self.admin_client:
            self.admin_client.close()
        self.executor.shutdown(wait=True)
