# RTSP Stream Output Management
# Handles streaming of annotated video frames via RTSP

# TODO: Implement RTSP streaming functions:
# - create_rtsp_stream(task_id, output_resolution): Initialize RTSP stream
# - stream_frame_to_rtsp(frame, stream_handle): Send frame to RTSP server
# - close_rtsp_stream(stream_handle): Clean up stream resources
# - get_rtsp_url(task_id): Get public RTSP URL for client access

# TODO: Add support for multiple concurrent streams
# TODO: Implement stream quality and bitrate control
# TODO: Add stream health monitoring and reconnection logic
# TODO: Consider alternative: save MP4 file instead of streaming 
"""
RTSP output management for streaming annotated video.
"""
import logging
import subprocess
import threading
from typing import Dict, Optional
import numpy as np
import queue
import time

logger = logging.getLogger(__name__)


class RTSPOutputManager:
    """Manages RTSP output streams for annotated videos."""
    
    def __init__(self, config: Dict):
        self.rtsp_server = config.get('server', 'localhost:8554')
        self.enable_rtsp = config.get('enable', True)
        self.streams = {}  # task_id -> stream_info
        self.output_queues = {}  # task_id -> frame queue
    
    def create_stream(self, task_id: str, width: int, height: int, fps: float) -> Optional[str]:
        """
        Create an RTSP output stream for a task.
        
        Args:
            task_id: Unique task identifier
            width: Video width
            height: Video height
            fps: Frames per second
            
        Returns:
            RTSP stream URL or None if disabled
        """
        if not self.enable_rtsp:
            logger.info("RTSP output disabled")
            return None
        
        stream_url = f"rtsp://{self.rtsp_server}/{task_id}"
        
        # Create frame queue
        self.output_queues[task_id] = queue.Queue(maxsize=30)
        
        # Start FFmpeg process for RTSP streaming
        # TODO: Implement actual FFmpeg streaming
        # This would typically use:
        # ffmpeg -f rawvideo -pix_fmt rgb24 -s {width}x{height} -r {fps} -i pipe:0 -c:v libx264 -f rtsp {stream_url}
        
        stream_info = {
            'task_id': task_id,
            'url': stream_url,
            'width': width,
            'height': height,
            'fps': fps,
            'process': None,
            'thread': None,
            'active': False
        }
        
        self.streams[task_id] = stream_info
        
        # Start streaming thread
        stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(task_id,),
            daemon=True
        )
        stream_thread.start()
        stream_info['thread'] = stream_thread
        stream_info['active'] = True
        
        logger.info(f"Created RTSP stream: {stream_url}")
        return stream_url
    
    def push_frame(self, task_id: str, frame: np.ndarray) -> bool:
        """
        Push a frame to the output stream.
        
        Args:
            task_id: Task identifier
            frame: Annotated frame (RGB)
            
        Returns:
            True if successful
        """
        if task_id not in self.output_queues:
            return False
        
        try:
            # Non-blocking put
            self.output_queues[task_id].put_nowait(frame)
            return True
        except queue.Full:
            logger.warning(f"Output queue full for task {task_id}, dropping frame")
            return False
    
    def _stream_worker(self, task_id: str):
        """Worker thread for streaming frames via FFmpeg."""
        stream_info = self.streams.get(task_id)
        if not stream_info:
            return
        
        try:
            # Build FFmpeg command
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'rgb24',
                '-s', f"{stream_info['width']}x{stream_info['height']}",
                '-r', str(stream_info['fps']),
                '-i', '-',  # Input from stdin
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-f', 'rtsp',
                stream_info['url']
            ]
            
            # TODO: Start FFmpeg process
            # process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            # stream_info['process'] = process
            
            logger.warning(f"TODO: Implement actual FFmpeg streaming for task {task_id}")
            
            # Process frames from queue
            frame_queue = self.output_queues[task_id]
            
            while stream_info['active']:
                try:
                    frame = frame_queue.get(timeout=1.0)
                    
                    # TODO: Write frame to FFmpeg stdin
                    # process.stdin.write(frame.tobytes())
                    # process.stdin.flush()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error streaming frame: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Stream worker error for task {task_id}: {e}")
        finally:
            self._cleanup_stream(task_id)
    
    def stop_stream(self, task_id: str):
        """Stop an RTSP stream."""
        if task_id not in self.streams:
            return
        
        stream_info = self.streams[task_id]
        stream_info['active'] = False
        
        # Wait for thread to finish
        if stream_info['thread']:
            stream_info['thread'].join(timeout=5.0)
        
        self._cleanup_stream(task_id)
        logger.info(f"Stopped RTSP stream for task {task_id}")
    
    def _cleanup_stream(self, task_id: str):
        """Clean up stream resources."""
        if task_id in self.streams:
            stream_info = self.streams[task_id]
            
            # Terminate FFmpeg process
            if stream_info.get('process'):
                try:
                    stream_info['process'].terminate()
                    stream_info['process'].wait(timeout=5)
                except:
                    stream_info['process'].kill()
            
            # Remove from tracking
            del self.streams[task_id]
        
        # Clear queue
        if task_id in self.output_queues:
            del self.output_queues[task_id]
    
    def cleanup_all(self):
        """Stop all streams and clean up."""
        task_ids = list(self.streams.keys())
        for task_id in task_ids:
            self.stop_stream(task_id)


class VideoFileWriter:
    """Writes annotated frames to video files."""
    
    def __init__(self, output_path: str, width: int, height: int, fps: float):
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.writer = None
        self._init_writer()
    
    def _init_writer(self):
        """Initialize video writer."""
        import cv2
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(
            self.output_path,
            fourcc,
            self.fps,
            (self.width, self.height)
        )
        
        if not self.writer.isOpened():
            raise RuntimeError(f"Failed to open video writer for {self.output_path}")
        
        logger.info(f"Initialized video writer: {self.output_path}")
    
    def write_frame(self, frame: np.ndarray):
        """Write a frame to the video file."""
        if self.writer and self.writer.isOpened():
            # Convert RGB to BGR for OpenCV
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            self.writer.write(bgr_frame)
    
    def release(self):
        """Release video writer resources."""
        if self.writer:
            self.writer.release()
            logger.info(f"Released video writer: {self.output_path}")