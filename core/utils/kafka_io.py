"""
Kafka I/O utilities for message production and consumption.
"""
import json
import logging
from typing import Dict, Optional, Callable, List
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
import numpy as np

logger = logging.getLogger(__name__)


class KafkaMessageProducer:
    """Handles Kafka message production with proper serialization."""
    
    def __init__(self, bootstrap_servers: str = 'localhost:9092'):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_request_size=52428800,  # 50MB for large images
            buffer_memory=104857600,    # 100MB buffer
            compression_type='gzip'
        )
    
    def send_message(self, topic: str, message: Dict) -> bool:
        """Send a message to a Kafka topic."""
        try:
            future = self.producer.send(topic, value=message)
            record_metadata = future.get(timeout=10)
            logger.debug(f"Message sent to {topic} partition {record_metadata.partition} "
                        f"offset {record_metadata.offset}")
            return True
        except KafkaError as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            return False
    
    def close(self):
        """Close the producer connection."""
        self.producer.flush()
        self.producer.close()


class KafkaMessageConsumer:
    """Handles Kafka message consumption with proper deserialization."""
    
    def __init__(self, 
                 topics: List[str],
                 group_id: str,
                 bootstrap_servers: str = 'localhost:9092',
                 auto_offset_reset: str = 'earliest'):
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            max_poll_records=1,  # Process one at a time for real-time
            enable_auto_commit=True
        )
        self.topics = topics
    
    def consume_messages(self, 
                        process_func: Callable[[Dict], None],
                        error_handler: Optional[Callable[[Exception], None]] = None):
        """
        Consume messages and process them with the provided function.
        
        Args:
            process_func: Function to process each message
            error_handler: Optional error handling function
        """
        try:
            for message in self.consumer:
                try:
                    logger.debug(f"Received message from {message.topic} "
                               f"partition {message.partition} offset {message.offset}")
                    process_func(message.value)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    if error_handler:
                        error_handler(e)
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
        finally:
            self.close()
    
    def close(self):
        """Close the consumer connection."""
        self.consumer.close()


class KafkaTopicManager:
    """Manages Kafka topic operations for dynamic topic creation/deletion."""
    
    def __init__(self, bootstrap_servers: str = 'localhost:9092'):
        from kafka.admin import KafkaAdminClient
        self.admin = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            client_id='topic_manager'
        )
    
    def create_task_topics(self, task_id: str) -> bool:
        """Create all topics for a specific task."""
        from kafka.admin import NewTopic
        
        topic_configs = {
            "retention.ms": "600000",      # 10 minutes
            "segment.bytes": "104857600",  # 100MB
            "cleanup.policy": "delete"
        }
        
        topic_prefixes = ["raw_frames", "yolox", "rtmpose", "bytetrack"]
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
            for topic, f in fs.items():
                try:
                    f.result()
                    logger.info(f"Topic {topic} created successfully")
                except Exception as e:
                    logger.error(f"Failed to create topic {topic}: {e}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Failed to create topics: {e}")
            return False
    
    def delete_task_topics(self, task_id: str) -> bool:
        """Delete all topics for a specific task."""
        topic_prefixes = ["raw_frames", "yolox", "rtmpose", "bytetrack"]
        topics = [f"{prefix}_{task_id}" for prefix in topic_prefixes]
        
        try:
            fs = self.admin.delete_topics(topics=topics)
            for topic, f in fs.items():
                try:
                    f.result()
                    logger.info(f"Topic {topic} deleted successfully")
                except Exception as e:
                    logger.error(f"Failed to delete topic {topic}: {e}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Failed to delete topics: {e}")
            return False
    
    def close(self):
        """Close admin client."""
        self.admin.close()