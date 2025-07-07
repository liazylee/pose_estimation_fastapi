"""
Kafka topic management utilities for contanos framework.
"""
import logging
from typing import List, Optional

try:
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError, UnknownTopicOrPartitionError
    KAFKA_ADMIN_AVAILABLE = True
except ImportError:
    KAFKA_ADMIN_AVAILABLE = False
    logging.warning("kafka-python admin not available. Install with: pip install kafka-python")

logger = logging.getLogger(__name__)


class KafkaTopicManager:
    """Manages Kafka topic operations for dynamic topic creation/deletion."""
    
    def __init__(self, bootstrap_servers: str = 'localhost:9092'):
        if not KAFKA_ADMIN_AVAILABLE:
            raise ImportError("kafka-python package is required. Install with: pip install kafka-python")
            
        self.bootstrap_servers = bootstrap_servers
        self.admin = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            client_id='contanos_topic_manager'
        )
    
    def create_task_topics(self, task_id: str, 
                          topic_prefixes: Optional[List[str]] = None) -> bool:
        """
        Create all topics for a specific task.
        
        Args:
            task_id: Task identifier
            topic_prefixes: List of topic prefixes. Defaults to pose estimation topics.
            
        Returns:
            True if all topics created successfully, False otherwise
        """
        if topic_prefixes is None:
            topic_prefixes = ["raw_frames", "yolox", "rtmpose", "bytetrack"]
        
        topic_configs = {
            "retention.ms": "600000",      # 10 minutes
            "segment.bytes": "104857600",  # 100MB
            "cleanup.policy": "delete"
        }
        
        topics = [
            NewTopic(
                name=f"{prefix}_{task_id}",
                num_partitions=1,
                replication_factor=1,
                topic_configs=topic_configs
            )
            for prefix in topic_prefixes
        ]
        
        try:
            fs = self.admin.create_topics(new_topics=topics, validate_only=False)
            all_success = True
            
            for topic, f in fs.items():
                try:
                    f.result()
                    logger.info(f"Topic {topic} created successfully")
                except TopicAlreadyExistsError:
                    logger.info(f"Topic {topic} already exists")
                except Exception as e:
                    logger.error(f"Failed to create topic {topic}: {e}")
                    all_success = False
                    
            return all_success
            
        except Exception as e:
            logger.error(f"Failed to create topics: {e}")
            return False
    
    def delete_task_topics(self, task_id: str,
                          topic_prefixes: Optional[List[str]] = None) -> bool:
        """
        Delete all topics for a specific task.
        
        Args:
            task_id: Task identifier
            topic_prefixes: List of topic prefixes. Defaults to pose estimation topics.
            
        Returns:
            True if all topics deleted successfully, False otherwise
        """
        if topic_prefixes is None:
            topic_prefixes = ["raw_frames", "yolox", "rtmpose", "bytetrack"]
            
        topics = [f"{prefix}_{task_id}" for prefix in topic_prefixes]
        
        try:
            fs = self.admin.delete_topics(topics=topics)
            all_success = True
            
            for topic, f in fs.items():
                try:
                    f.result()
                    logger.info(f"Topic {topic} deleted successfully")
                except UnknownTopicOrPartitionError:
                    logger.info(f"Topic {topic} does not exist")
                except Exception as e:
                    logger.error(f"Failed to delete topic {topic}: {e}")
                    all_success = False
                    
            return all_success
            
        except Exception as e:
            logger.error(f"Failed to delete topics: {e}")
            return False
    
    def list_topics(self, prefix: Optional[str] = None) -> List[str]:
        """
        List all topics, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter topics
            
        Returns:
            List of topic names
        """
        try:
            metadata = self.admin.describe_topics()
            topics = list(metadata.keys())
            
            if prefix:
                topics = [topic for topic in topics if topic.startswith(prefix)]
                
            return topics
            
        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            return []
    
    def topic_exists(self, topic_name: str) -> bool:
        """
        Check if a topic exists.
        
        Args:
            topic_name: Name of the topic to check
            
        Returns:
            True if topic exists, False otherwise
        """
        try:
            topics = self.list_topics()
            return topic_name in topics
        except Exception as e:
            logger.error(f"Failed to check topic existence: {e}")
            return False
    
    def close(self):
        """Close admin client."""
        try:
            self.admin.close()
        except Exception as e:
            logger.error(f"Error closing admin client: {e}") 