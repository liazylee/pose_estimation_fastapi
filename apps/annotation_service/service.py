"""
Annotation service for drawing pose overlays and generating output video.
"""
import logging
import signal
import json
import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import threading

from kafka import KafkaConsumer
from core.utils.serializers import deserialize_image_from_kafka
from .render import PoseRenderer
from .rtsp_output import RTSPOutputManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnnotationService:
    """Service for annotating frames with pose data and generating output."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.consumer = None
        self.running = True
        
        # Renderer and output manager
        self.renderer = PoseRenderer(config.get('render', {}))
        self.rtsp_manager = RTSPOutputManager(config.get('rtsp', {}))
        
        # Frame synchronization buffers
        self.frame_buffers = defaultdict(dict)  # task_id -> {frame_id -> data}
        self.pose_buffers = defaultdict(dict)   # task_id -> {frame_id -> data}
        self.output_writers = {}  # task_id -> video writer
        self.task_metadata = {}  # task_id -> metadata (fps, width, height, etc.)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def process_frame_message(self, topic: str, message: Dict):
        """Process raw frame messages."""
        task_id = message['task_id']
        frame_id = message['frame_id']
        
        # Store frame data
        self.frame_buffers[task_id][frame_id] = message
        
        # Initialize RTSP stream for task if not exists
        if task_id not in self.task_metadata and 'metadata' in message:
            metadata = message['metadata']
            self.task_metadata[task_id] = metadata
            
            # Create RTSP stream for this task
            stream_url = self.rtsp_manager.create_stream(
                task_id=task_id,
                width=int(metadata['original_width']),
                height=int(metadata['original_height']),
                fps=float(metadata['fps'])
            )
            
            if stream_url:
                logger.info(f"Created RTSP stream for task {task_id}: {stream_url}")
        
        # Check if we have matching pose data
        self._try_process_synchronized_data(task_id, frame_id)
    
    def process_pose_message(self, topic: str, message: Dict):
        """Process tracked pose messages."""
        task_id = message['task_id']
        frame_id = message['frame_id']
        
        # Store pose data
        self.pose_buffers[task_id][frame_id] = message
        
        # Check if we have matching frame data
        self._try_process_synchronized_data(task_id, frame_id)
    
    def _try_process_synchronized_data(self, task_id: str, frame_id: int):
        """Try to process synchronized frame and pose data."""
        if (frame_id in self.frame_buffers[task_id] and 
            frame_id in self.pose_buffers[task_id]):
            
            # Get synchronized data
            frame_data = self.frame_buffers[task_id].pop(frame_id)
            pose_data = self.pose_buffers[task_id].pop(frame_id)
            
            # Process the synchronized data
            self._annotate_and_output(task_id, frame_data, pose_data)
            
            # Clean up old buffered data
            self._cleanup_buffers(task_id, frame_id)
    
    def _annotate_and_output(self, task_id: str, 
                            frame_data: Dict, 
                            pose_data: Dict):
        """Annotate frame with pose data and output."""
        try:
            # Deserialize frame
            frame = deserialize_image_from_kafka(
                frame_data['image_bytes'],
                is_base64=True
            )
            
            # Get tracked poses
            tracked_poses = pose_data.get('tracked_poses', [])
            
            # Render annotations
            annotated_frame = self.renderer.render_frame(
                frame, 
                tracked_poses,
                frame_data.get('metadata', {})
            )
            
            # Push annotated frame to RTSP stream
            success = self.rtsp_manager.push_frame(task_id, annotated_frame)
            
            if frame_data['frame_id'] % 30 == 0:  # Log every 30 frames
                logger.info(f"Annotated and streamed frame {frame_data['frame_id']} for task {task_id}, "
                           f"rendered {len(tracked_poses)} people, stream_success: {success}")
            
        except Exception as e:
            logger.error(f"Error annotating frame: {e}")
    
    def _cleanup_buffers(self, task_id: str, current_frame: int):
        """Remove old buffered data to prevent memory issues."""
        buffer_size_limit = 30  # Keep max 30 frames in buffer
        
        for buffer in [self.frame_buffers[task_id], self.pose_buffers[task_id]]:
            if len(buffer) > buffer_size_limit:
                # Remove frames older than current - buffer_size
                frames_to_remove = [
                    fid for fid in buffer.keys() 
                    if fid < current_frame - buffer_size_limit
                ]
                for fid in frames_to_remove:
                    buffer.pop(fid, None)
    
    def start(self):
        """Start the annotation service."""
        logger.info("Starting Annotation service...")
        
        try:
            # Create multi-topic consumer
            self.consumer = KafkaConsumer(
                bootstrap_servers=self.config['kafka']['bootstrap_servers'],
                group_id='annotation_service',
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                enable_auto_commit=True
            )
            
            # Subscribe to both raw frames and bytetrack topics
            patterns = [
                re.compile(r'^raw_frames_.*'),
                re.compile(r'^bytetrack_.*')
            ]
            
            # Subscribe to all matching topics
            all_topics = []
            for pattern in patterns:
                self.consumer.subscribe(pattern=pattern)
            
            logger.info("Annotation service started, waiting for data...")
            
            # Process messages
            for message in self.consumer:
                if not self.running:
                    break
                
                topic = message.topic
                
                if topic.startswith('raw_frames_'):
                    self.process_frame_message(topic, message.value)
                elif topic.startswith('bytetrack_'):
                    self.process_pose_message(topic, message.value)
                
        except Exception as e:
            logger.error(f"Service error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up Annotation service...")
        
        # Close all video writers
        for writer in self.output_writers.values():
            if writer:
                writer.release()
        
        # Clear buffers
        self.frame_buffers.clear()
        self.pose_buffers.clear()
        
        if self.consumer:
            self.consumer.close()
        
        logger.info("Annotation service stopped")


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
            "render": {
                "show_track_id": True,
                "show_keypoints": True,
                "show_skeleton": True,
                "keypoint_radius": 3,
                "skeleton_thickness": 2,
                "font_scale": 0.5
            },
            "rtsp": {
                "server": "localhost:8554",
                "enable": True
            }
        }
    
    # Start service
    service = AnnotationService(config)
    service.start()


if __name__ == "__main__":
    main()