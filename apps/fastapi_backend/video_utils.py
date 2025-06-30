# Video Processing Utilities
# Functions for video frame extraction and Kafka publishing

# TODO: Implement the following functions:
# - extract_frames_and_publish(video_path, task_id): Main frame processing function
# - extract_frame_from_video(video_path): Generator for video frames
# - compress_frame_to_jpeg(frame): Convert frame to JPEG format
# - publish_frame_to_kafka(frame_data, task_id, frame_id): Send frame to Kafka
# - validate_video_format(file_path): Check if uploaded file is valid video

# TODO: Add support for different video formats (MP4, AVI, MOV, etc.)
# TODO: Add frame rate control and optimization
# TODO: Handle video metadata extraction 
"""
Video processing utilities for frame extraction and publishing.
"""
import cv2
import logging
import time
from pathlib import Path
from typing import Optional, Generator, Tuple
import numpy as np

from core.utils.kafka_io import KafkaMessageProducer
from core.utils.serializers import serialize_image_for_kafka, resize_frame_if_needed

logger = logging.getLogger(__name__)


class VideoFrameExtractor:
    """Extract frames from video files."""
    
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.cap = None
        self.fps = 0
        self.frame_count = 0
        self.width = 0
        self.height = 0
        self._open_video()
    
    def _open_video(self):
        """Open video file and extract metadata."""
        self.cap = cv2.VideoCapture(self.video_path)
        
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open video: {self.video_path}")
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        logger.info(f"Opened video: {self.width}x{self.height} @ {self.fps}fps, {self.frame_count} frames")
    
    def extract_frames(self, 
                      skip_frames: int = 0,
                      max_frames: Optional[int] = None) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Extract frames from video.
        
        Args:
            skip_frames: Process every Nth frame (0 = process all)
            max_frames: Maximum frames to extract
            
        Yields:
            Tuple of (frame_id, frame_array)
        """
        frame_id = 0
        processed = 0
        
        while True:
            ret, frame = self.cap.read()
            
            if not ret:
                break
            
            # Skip frames if requested
            if skip_frames > 0 and frame_id % (skip_frames + 1) != 0:
                frame_id += 1
                continue
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            yield frame_id, rgb_frame
            
            frame_id += 1
            processed += 1
            
            if max_frames and processed >= max_frames:
                break
    
    def close(self):
        """Release video capture resources."""
        if self.cap:
            self.cap.release()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def extract_frames_and_publish(video_path: str, 
                             task_id: str,
                             bootstrap_servers: str = "localhost:9092",
                             resize_max: int = 1920,
                             skip_frames: int = 0,
                             jpeg_quality: int = 85):
    """
    Extract frames from video and publish to Kafka.
    
    Args:
        video_path: Path to video file
        task_id: Unique task identifier
        bootstrap_servers: Kafka broker address
        resize_max: Maximum dimension for frame resizing
        skip_frames: Process every Nth frame
        jpeg_quality: JPEG compression quality
    """
    producer = KafkaMessageProducer(bootstrap_servers)
    topic = f"raw_frames_{task_id}"
    source_id = Path(video_path).stem
    
    try:
        with VideoFrameExtractor(video_path) as extractor:
            total_frames = extractor.frame_count
            fps = extractor.fps
            
            for frame_id, frame in extractor.extract_frames(skip_frames):
                # Resize if needed
                resized_frame, scale = resize_frame_if_needed(frame, resize_max)
                
                # Calculate timestamp
                timestamp_seconds = frame_id / fps
                timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(timestamp_seconds))
                timestamp += f".{int((timestamp_seconds % 1) * 1000):03d}Z"
                
                # Prepare message
                message = {
                    "task_id": task_id,
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "source_id": source_id,
                    "image_format": "jpeg",
                    "image_bytes": serialize_image_for_kafka(resized_frame, use_base64=True, quality=jpeg_quality),
                    "metadata": {
                        "original_width": extractor.width,
                        "original_height": extractor.height,
                        "scale_factor": scale,
                        "fps": fps,
                        "total_frames": total_frames
                    }
                }
                
                # Send to Kafka
                success = producer.send_message(topic, message)
                
                if not success:
                    logger.error(f"Failed to send frame {frame_id} to Kafka")
                else:
                    if frame_id % 30 == 0:  # Log every 30 frames
                        progress = (frame_id / total_frames) * 100
                        logger.info(f"Published frame {frame_id}/{total_frames} ({progress:.1f}%)")
            
            logger.info(f"Completed publishing {total_frames} frames for task {task_id}")
            
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        raise
    finally:
        producer.close()


class RTSPStreamManager:
    """Manage RTSP output streams."""
    
    def __init__(self, rtsp_server: str = "localhost:8554"):
        self.rtsp_server = rtsp_server
        self.active_streams = {}
    
    def create_stream(self, task_id: str, width: int, height: int, fps: float) -> str:
        """
        Create an RTSP stream for a task.
        
        Args:
            task_id: Unique task identifier
            width: Video width
            height: Video height
            fps: Frames per second
            
        Returns:
            RTSP stream URL
        """
        stream_url = f"rtsp://{self.rtsp_server}/{task_id}"
        
        # TODO: Implement actual RTSP stream creation
        # This would typically use FFmpeg or GStreamer
        # For now, we'll store the configuration
        
        self.active_streams[task_id] = {
            "url": stream_url,
            "width": width,
            "height": height,
            "fps": fps,
            "created_at": time.time()
        }
        
        logger.info(f"Created RTSP stream: {stream_url}")
        return stream_url
    
    def stop_stream(self, task_id: str):
        """Stop an RTSP stream."""
        if task_id in self.active_streams:
            # TODO: Implement actual stream stopping
            del self.active_streams[task_id]
            logger.info(f"Stopped RTSP stream for task {task_id}")