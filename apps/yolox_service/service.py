# YOLOX Service Core Logic
# Handles Kafka I/O and model inference coordination

# TODO: Implement YOLOXService class:
# - Kafka consumer setup for raw frames
# - Kafka producer setup for detections
# - Frame processing pipeline
# - Error handling and recovery
# - Dynamic topic subscription based on task patterns

# TODO: Integrate with core.models.yolox_model
# TODO: Add message validation and serialization
# TODO: Implement graceful shutdown handling 
"""
YOLOX service for human detection in video frames.
"""
import logging
import signal
import sys
from typing import Dict, List

from core.utils.kafka_io import KafkaMessageConsumer, KafkaMessageProducer
from core.utils.serializers import deserialize_image_from_kafka
from core.models.yolox_model import YOLOXModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YOLOXService:
    """Service for running YOLOX detection on video frames."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.model = YOLOXModel(config['model'])
        self.producer = KafkaMessageProducer(config['kafka']['bootstrap_servers'])
        self.consumer = None
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def process_frame(self, message: Dict):
        """
        Process a single frame through YOLOX.
        
        Args:
            message: Kafka message containing frame data
        """
        if not self.running:
            return
        
        try:
            # Extract message data
            task_id = message['task_id']
            frame_id = message['frame_id']
            timestamp = message['timestamp']
            
            # Deserialize image
            image = deserialize_image_from_kafka(
                message['image_bytes'], 
                is_base64=True
            )
            
            # Run detection
            input_data = {
                "task_id": task_id,
                "frame_id": frame_id,
                "timestamp": timestamp,
                "image": image
            }
            
            result = self.model.predict(input_data)
            
            # Prepare output message
            output_message = {
                "task_id": task_id,
                "frame_id": frame_id,
                "timestamp": timestamp,
                "detections": result['result']
            }
            
            # Send to output topic
            output_topic = f"yolox_{task_id}"
            self.producer.send_message(output_topic, output_message)
            
            logger.debug(f"Processed frame {frame_id} for task {task_id}, "
                        f"found {len(result['result'])} detections")
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
    
    def start(self):
        """Start the YOLOX service."""
        logger.info("Starting YOLOX service...")
        
        # Subscribe to all raw_frames topics
        # In production, this would use a pattern subscription
        # For now, we'll handle dynamic subscription
        
        try:
            from kafka import KafkaConsumer
            
            # Create a pattern-based consumer
            self.consumer = KafkaConsumer(
                bootstrap_servers=self.config['kafka']['bootstrap_servers'],
                group_id='yolox_service',
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                enable_auto_commit=True
            )
            
            # Subscribe to pattern
            import re
            pattern = re.compile(r'^raw_frames_.*')
            self.consumer.subscribe(pattern=pattern)
            
            logger.info("YOLOX service started, waiting for frames...")
            
            # Process messages
            for message in self.consumer:
                if not self.running:
                    break
                    
                self.process_frame(message.value)
                
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up YOLOX service...")
        
        if self.consumer:
            self.consumer.close()
        
        if self.producer:
            self.producer.close()
        
        logger.info("YOLOX service stopped")


def main():
    """Main entry point."""
    import yaml
    import json
    
    # Load configuration
    config_path = "config.yaml"
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        # Use default config
        config = {
            "kafka": {
                "bootstrap_servers": "localhost:9092"
            },
            "model": {
                "weights": "/models/yolox_s.pth",
                "device": "cuda",
                "confidence_threshold": 0.5,
                "nms_threshold": 0.45
            }
        }
    
    # Start service
    service = YOLOXService(config)
    service.start()


if __name__ == "__main__":
    main()