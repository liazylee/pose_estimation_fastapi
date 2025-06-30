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
RTMPose service for pose estimation on detected humans.
"""
import logging
import signal
import json
import re
from typing import Dict, List

from kafka import KafkaConsumer
from core.utils.kafka_io import KafkaMessageProducer
from core.utils.serializers import deserialize_image_from_kafka
from core.models.rtmpose_model import RTMPoseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RTMPoseService:
    """Service for running RTMPose estimation on detected humans."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.model = RTMPoseModel(config['model'])
        self.producer = KafkaMessageProducer(config['kafka']['bootstrap_servers'])
        self.consumer = None
        self.running = True
        
        # Track frame data for synchronization
        self.frame_cache = {}
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def process_detections(self, message: Dict):
        """
        Process detections through RTMPose.
        
        Args:
            message: Kafka message containing detection data
        """
        if not self.running:
            return
        
        try:
            task_id = message['task_id']
            frame_id = message['frame_id']
            timestamp = message['timestamp']
            detections = message['detections']
            
            # We need the original frame for pose estimation
            # In a production system, you might:
            # 1. Cache frames temporarily
            # 2. Have a separate consumer for raw_frames
            # 3. Use a shared storage system
            
            # For now, we'll process with mock data
            # TODO: Implement frame synchronization
            
            if not detections:
                # No people detected, send empty result
                output_message = {
                    "task_id": task_id,
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "poses": []
                }
            else:
                # Process each detection
                poses = []
                for detection in detections:
                    # In production, crop the image using bbox and run pose estimation
                    # For now, we'll generate mock keypoints
                    
                    bbox = detection['bbox']
                    keypoints = self._generate_mock_keypoints(bbox)
                    
                    poses.append({
                        "person_id": detection['person_id'],
                        "bbox": bbox,
                        "keypoints": keypoints
                    })
                
                output_message = {
                    "task_id": task_id,
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "poses": poses
                }
            
            # Send to output topic
            output_topic = f"rtmpose_{task_id}"
            self.producer.send_message(output_topic, output_message)
            
            logger.debug(f"Processed frame {frame_id} for task {task_id}, "
                        f"estimated {len(poses)} poses")
            
        except Exception as e:
            logger.error(f"Error processing detections: {e}")
    
    def _generate_mock_keypoints(self, bbox: List[float]) -> List[List[float]]:
        """Generate mock keypoints for testing."""
        # COCO 17 keypoints format
        # In production, this would be actual pose estimation
        x, y, w, h = bbox
        cx, cy = x + w/2, y + h/2
        
        # Simple skeleton layout
        keypoints = [
            [cx, y + h*0.1, 0.9],           # nose
            [cx - w*0.15, y + h*0.15, 0.85], # left_eye
            [cx + w*0.15, y + h*0.15, 0.85], # right_eye
            [cx - w*0.2, y + h*0.2, 0.8],   # left_ear
            [cx + w*0.2, y + h*0.2, 0.8],   # right_ear
            [cx - w*0.3, y + h*0.3, 0.75],  # left_shoulder
            [cx + w*0.3, y + h*0.3, 0.75],  # right_shoulder
            [cx - w*0.25, y + h*0.5, 0.7],  # left_elbow
            [cx + w*0.25, y + h*0.5, 0.7],  # right_elbow
            [cx - w*0.2, y + h*0.7, 0.65],  # left_wrist
            [cx + w*0.2, y + h*0.7, 0.65],  # right_wrist
            [cx - w*0.15, y + h*0.5, 0.7],  # left_hip
            [cx + w*0.15, y + h*0.5, 0.7],  # right_hip
            [cx - w*0.1, y + h*0.7, 0.65],  # left_knee
            [cx + w*0.1, y + h*0.7, 0.65],  # right_knee
            [cx - w*0.1, y + h*0.9, 0.6],   # left_ankle
            [cx + w*0.1, y + h*0.9, 0.6],   # right_ankle
        ]
        
        return keypoints
    
    def start(self):
        """Start the RTMPose service."""
        logger.info("Starting RTMPose service...")
        
        try:
            # Create pattern-based consumer for YOLOX topics
            self.consumer = KafkaConsumer(
                bootstrap_servers=self.config['kafka']['bootstrap_servers'],
                group_id='rtmpose_service',
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                enable_auto_commit=True
            )
            
            # Subscribe to YOLOX output topics
            pattern = re.compile(r'^yolox_.*')
            self.consumer.subscribe(pattern=pattern)
            
            logger.info("RTMPose service started, waiting for detections...")
            
            # Process messages
            for message in self.consumer:
                if not self.running:
                    break
                    
                self.process_detections(message.value)
                
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up RTMPose service...")
        
        if self.consumer:
            self.consumer.close()
        
        if self.producer:
            self.producer.close()
        
        logger.info("RTMPose service stopped")


def main():
    """Main entry point."""
    import yaml
    
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
                "weights": "/models/rtmpose_m_body8_256x192.pth",
                "device": "cuda",
                "confidence_threshold": 0.5
            }
        }
    
    # Start service
    service = RTMPoseService(config)
    service.start()


if __name__ == "__main__":
    main()