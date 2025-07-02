"""
Video processing utilities for frame extraction and publishing.
"""
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Generator, Tuple

import cv2
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
                               jpeg_quality: int = 90):
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

    def create_stream_from_video(self, task_id: str, video_path: str) -> str:
        """
        Create an RTSP stream from a video file.
        
        Args:
            task_id: Unique task identifier
            video_path: Path to video file
            
        Returns:
            RTSP stream URL
        """
        stream_url = f"rtsp://{self.rtsp_server}/{task_id}"

        # FFmpeg command to stream video file to RTSP
        ffmpeg_cmd = [
            'ffmpeg',
            '-re',  # Read input at native frame rate
            '-i', video_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            stream_url
        ]

        # Start FFmpeg process in background thread
        def start_ffmpeg_stream():
            try:
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.active_streams[task_id]['ffmpeg_process'] = process

                # Wait for process to complete or be terminated
                stdout, stderr = process.communicate()

                if process.returncode != 0:
                    logger.error(f"FFmpeg stream error for task {task_id}: {stderr.decode()}")
                else:
                    logger.info(f"FFmpeg stream completed for task {task_id}")

            except Exception as e:
                logger.error(f"Failed to start FFmpeg stream for task {task_id}: {e}")

        # Start stream in background thread
        stream_thread = threading.Thread(target=start_ffmpeg_stream)
        stream_thread.daemon = True
        stream_thread.start()

        self.active_streams[task_id] = {
            "rtsp_url": stream_url,
            "video_path": video_path,
            "created_at": time.time(),
            "thread": stream_thread,
            "active": True,
            "error": None
        }

        logger.info(f"Created RTSP stream from video: {stream_url}")
        return stream_url

    def create_live_stream(self, task_id: str, width: int, height: int, fps: float) -> str:
        """
        Create a live RTSP stream that can accept frame data.
        
        Args:
            task_id: Unique task identifier
            width: Video width
            height: Video height
            fps: Frames per second
            
        Returns:
            RTSP stream URL
        """
        stream_url = f"rtsp://{self.rtsp_server}/{task_id}"

        # FFmpeg command to create live RTSP stream from pipe input
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'rgb24',
            '-s', f'{width}x{height}',
            '-r', str(fps),
            '-i', '-',  # Input from stdin
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            stream_url
        ]

        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            self.active_streams[task_id] = {
                "url": stream_url,
                "width": width,
                "height": height,
                "fps": fps,
                "created_at": time.time(),
                "ffmpeg_process": process,
                "is_live": True
            }

            logger.info(f"Created live RTSP stream: {stream_url}")
            return stream_url

        except Exception as e:
            logger.error(f"Failed to create live RTSP stream for task {task_id}: {e}")
            return None

    def push_frame(self, task_id: str, frame: np.ndarray) -> bool:
        """
        Push a frame to the live RTSP stream.
        
        Args:
            task_id: Task identifier
            frame: Frame data (RGB format)
            
        Returns:
            True if successful
        """
        if task_id not in self.active_streams:
            return False

        stream_info = self.active_streams[task_id]

        if not stream_info.get('is_live') or 'ffmpeg_process' not in stream_info:
            return False

        try:
            # Write frame data to ffmpeg stdin
            frame_bytes = frame.tobytes()
            stream_info['ffmpeg_process'].stdin.write(frame_bytes)
            stream_info['ffmpeg_process'].stdin.flush()
            return True

        except Exception as e:
            logger.error(f"Error pushing frame to stream {task_id}: {e}")
            return False

    def create_stream(self, task_id: str, width: int, height: int, fps: float, loop: bool = True) -> str:
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

        # Create RTSP stream using FFmpeg

        # FFmpeg command to create RTSP stream
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'testsrc2=size={width}x{height}:rate={fps}',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp'
        ]

        # Add loop parameter if specified
        if loop:
            ffmpeg_cmd.extend(['-stream_loop', '-1'])

        ffmpeg_cmd.append(f'rtsp://{self.rtsp_server}/{task_id}')

        # Start FFmpeg process in background thread
        def start_ffmpeg_stream():
            try:
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                # Store process for later termination
                self.active_streams[task_id]['ffmpeg_process'] = process
                logger.info(f"Started FFmpeg RTSP stream for task {task_id} (loop: {loop})")
            except Exception as e:
                logger.error(f"Failed to start FFmpeg stream for task {task_id}: {e}")

        # Start stream in background thread
        stream_thread = threading.Thread(target=start_ffmpeg_stream)
        stream_thread.daemon = True
        stream_thread.start()
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
            # Stop FFmpeg process if it exists
            if 'ffmpeg_process' in self.active_streams[task_id]:
                try:
                    # Close stdin if it's a live stream
                    if self.active_streams[task_id].get('is_live'):
                        self.active_streams[task_id]['ffmpeg_process'].stdin.close()

                    self.active_streams[task_id]['ffmpeg_process'].terminate()
                    self.active_streams[task_id]['ffmpeg_process'].wait(timeout=5)
                    logger.info(f"Terminated FFmpeg process for task {task_id}")
                except subprocess.TimeoutExpired:
                    self.active_streams[task_id]['ffmpeg_process'].kill()
                    logger.warning(f"Force killed FFmpeg process for task {task_id}")
                except Exception as e:
                    logger.error(f"Error stopping FFmpeg process for task {task_id}: {e}")
            del self.active_streams[task_id]
            logger.info(f"Stopped RTSP stream for task {task_id}")

    def get_active_streams(self):
        """Get list of active streams."""
        return list(self.active_streams.keys())

    def is_stream_active(self, task_id: str) -> bool:
        """Check if a stream is active."""
        return task_id in self.active_streams

    def get_stream_status(self, task_id: str = None) -> Optional[dict]:
        """
        Get status of a specific stream.

        Args:
            task_id: Unique task identifier

        Returns:
            Stream info dictionary or None if not found
        """
        if not task_id:
            return self.active_streams
        return self.active_streams.get(task_id, None)
