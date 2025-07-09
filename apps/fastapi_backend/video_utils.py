"""
Video processing utilities for frame extraction and publishing.
Updated to use contanos serialization utilities.
"""
import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Generator, Tuple, Dict

import cv2
import numpy as np

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.io.kafka_output_interface import KafkaOutput
from contanos.utils.serializers import serialize_image_for_kafka, resize_frame_if_needed

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
                       start_frame: int = 0,
                       max_frames: Optional[int] = None) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Extract frames from video.

        Args:
            start_frame: Start frame number
            max_frames: Maximum number of frames to extract

        Yields:
            Tuple of (frame_number, frame_array)
        """
        if not self.cap:
            raise ValueError("Video not opened")

        # Seek to start frame
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        frame_count = 0
        current_frame = start_frame

        while True:
            ret, frame = self.cap.read()

            if not ret:
                break

            if max_frames and frame_count >= max_frames:
                break

            yield current_frame, frame
            frame_count += 1
            current_frame += 1

    def get_metadata(self) -> dict:
        """Get video metadata."""
        return {
            'fps': self.fps,
            'frame_count': self.frame_count,
            'width': self.width,
            'height': self.height,
            'duration': self.frame_count / self.fps if self.fps > 0 else 0
        }

    def close(self):
        """Close video capture."""
        if self.cap:
            self.cap.release()
            self.cap = None


class VideoStreamPublisher:
    """Publish video frames to Kafka topics."""

    def __init__(self,
                 task_id: str,
                 kafka_config: dict,
                 fps: float = 30.0,
                 max_dimension: int = 1920):
        self.task_id = task_id
        self.kafka_config = kafka_config
        self.fps = fps
        self.max_dimension = max_dimension
        self.frame_interval = 1.0 / fps

        # Initialize Kafka output using contanos
        self.kafka_output = None
        self.is_publishing = False
        self.publish_thread = None

    async def initialize(self):
        """Initialize Kafka connection."""
        try:
            self.kafka_output = KafkaOutput(config=self.kafka_config)
            await self.kafka_output.initialize()
            logger.info(f"Kafka output initialized for task {self.task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Kafka output: {e}")
            return False

    async def publish_video_frames(self, video_path: str,
                                   start_frame: int = 0,
                                   max_frames: Optional[int] = None):
        """
        Publish video frames to Kafka topic.

        Args:
            video_path: Path to video file
            start_frame: Start frame number
            max_frames: Maximum frames to publish
        """
        try:
            extractor = VideoFrameExtractor(video_path)
            frame_id = start_frame
            start_time = time.time()

            for current_frame, frame in extractor.extract_frames(start_frame, max_frames):
                if not self.is_publishing:
                    break
                processed_frame, scale = resize_frame_if_needed(frame, self.max_dimension)
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                message = {
                    "task_id": self.task_id,
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "source_id": Path(video_path).name,
                    "image_format": "jpeg",
                    "image_bytes": serialize_image_for_kafka(processed_frame, use_base64=True, quality=90),
                    "metadata": {
                        "original_width": extractor.width,
                        "original_height": extractor.height,
                        "scale_factor": scale,
                        "fps": extractor.fps
                    }
                }
                await self.kafka_output.write_data(message)
                frame_id += 1
                elapsed = time.time() - start_time
                expected_time = (frame_id - start_frame) * self.frame_interval
                if elapsed < expected_time:
                    await asyncio.sleep(expected_time - elapsed)
                if frame_id % 100 == 0:
                    logger.info(f"published {frame_id - start_frame} frames for task {self.task_id}")
            extractor.close()
            logger.info(f"Published {frame_id - start_frame} frames for task {self.task_id} from {video_path}")
        except Exception as e:
            logger.error(f"Error publishing video frames for task {self.task_id}: {e}")
            raise

    def start_publishing(self, video_path: str, **kwargs):
        """Start publishing in background thread."""
        if self.is_publishing:
            logger.warning("Publishing already in progress")
            return

        self.is_publishing = True
        self.publish_thread = threading.Thread(
            target=self._publish_worker,
            args=(video_path,),
            kwargs=kwargs
        )
        self.publish_thread.start()
        logger.info(f"Started publishing video frames for task {self.task_id}")

    def _publish_worker(self, video_path: str, **kwargs):
        """Worker thread for publishing frames."""
        import asyncio

        try:
            # Create event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run publishing
            loop.run_until_complete(self.publish_video_frames(video_path, **kwargs))

        except Exception as e:
            logger.error(f"Error in publish worker: {e}")
        finally:
            loop.close()

    def stop_publishing(self):
        """Stop publishing frames."""
        self.is_publishing = False

        if self.publish_thread and self.publish_thread.is_alive():
            self.publish_thread.join(timeout=5.0)
            logger.info(f"Stopped publishing for task {self.task_id}")

    async def cleanup(self):
        """Cleanup resources."""
        self.stop_publishing()

        if self.kafka_output:
            await self.kafka_output.cleanup()


class RTSPStreamManager:
    """Manager for multiple RTSP streams."""

    def __init__(self, rtsp_server_url: str = "rtsp://localhost:8554"):
        self.streams: Dict[str, subprocess.Popen] = {}
        self.stream_configs: Dict[str, dict] = {}
        self.rtsp_server_url = rtsp_server_url
        logger.info("RTSP Stream Manager initialized")

    def create_stream_from_video(self, task_id: str, video_path: str) -> Optional[str]:
        """
         ustilize FFmpeg to create an RTSP stream from a video file.
         Args:
             task_id: Unique identifier for the task
             video_path: Path to the video file
         Returns:
             RTSP URL if successful, None otherwise


        """
        if task_id in self.streams and self.is_stream_active(task_id):
            logger.warning(f"RTSP stream for task {task_id} already exists and is active.")
            return self.stream_configs[task_id]['rtsp_url']

        if not Path(video_path).exists():
            logger.error(f"Video file does not exist: {video_path}")
            return None

        rtsp_url = f"{self.rtsp_server_url}/{task_id}"

        ffmpeg_cmd = [
            'ffmpeg',
            '-re',  # 以原生帧率读取输入
            '-stream_loop', '-1',  # 无限循环视频
            '-i', video_path,  # 输入文件
            '-c', 'copy',  # 直接复制流（不重新编码）
            '-f', 'rtsp',  # 格式为RTSP
            rtsp_url,
        ]

        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            self.streams[task_id] = process
            self.stream_configs[task_id] = {
                'rtsp_url': rtsp_url,
                'video_path': video_path,
                'created_at': time.time(),
                'process_pid': process.pid
            }
            logger.info(f"task {task_id} RTSP stream created from video: {video_path}")
            return rtsp_url
        except Exception as e:
            logger.error(f"Failed to create RTSP stream for task {task_id} from video {video_path}: {e}")
            return None

    def is_stream_active(self, task_id: str) -> bool:
        """检查特定任务的流是否仍在运行。"""
        if task_id in self.streams:
            process = self.streams[task_id]
            if process.poll() is None:
                return True  # 进程仍在运行
            else:
                # 进程已终止，进行清理
                logger.warning(f"检测到任务 {task_id} 的流进程已终止。正在清理...")
                self.cleanup_stream(task_id)
                return False
        return False

    def stop_stream(self, task_id: str) -> bool:
        """停止特定任务的RTSP流。"""
        if task_id in self.streams:
            process = self.streams[task_id]
            logger.info(f"正在停止任务 {task_id} 的RTSP流 (PID: {process.pid})...")
            process.terminate()
            try:
                process.wait(timeout=5)  # 等待进程终止
                logger.info(f"任务 {task_id} 的流已成功终止。")
            except subprocess.TimeoutExpired:
                logger.warning(f"任务 {task_id} 的流在终止后未能退出，正在强制终止 (SIGKILL)...")
                process.kill()  # 发送SIGKILL
                logger.info(f"任务 {task_id} 的流已被强制终止。")

            # 从跟踪中移除
            self.cleanup_stream(task_id)
            return True
        else:
            logger.warning(f"尝试停止流，但未找到任务 {task_id} 的流。")
            return False

    def get_stream_status(self, task_id: str) -> Optional[dict]:
        """获取特定RTSP流的状态。"""
        if self.is_stream_active(task_id):
            config = self.stream_configs.get(task_id, {})
            return {
                "task_id": task_id,
                "active": True,
                "rtsp_url": config.get("rtsp_url"),
                "video_path": config.get("video_path"),
                "created_at": config.get("created_at"),
                "pid": config.get("process_pid")
            }
        return None

    def get_active_streams(self) -> Dict[str, dict]:
        """获取所有活动流的列表。"""
        active_streams = {}
        # 使用列表以避免在迭代时修改字典
        for task_id in list(self.streams.keys()):
            status = self.get_stream_status(task_id)
            if status and status.get("active"):
                active_streams[task_id] = status
        return active_streams

    def cleanup_stream(self, task_id: str):
        """清理特定任务的流资源。"""
        self.streams.pop(task_id, None)
        self.stream_configs.pop(task_id, None)
        logger.info(f"已清理任务 {task_id} 的RTSP流资源。")

    def cleanup_all(self):
        """清理所有流。"""
        task_ids = list(self.streams.keys())
        for task_id in task_ids:
            self.stop_stream(task_id)
        logger.info("所有RTSP流已清理。")


# Convenience function for backward compatibility
def extract_frames_and_publish(video_path: str,
                               task_id: str,
                               skip_frames: int = 0,
                               jpeg_quality: int = 85):
    """从视频中提取帧并发布到Kafka的便捷函数。"""

    async def _async_extract_and_publish():
        kafka_config = {
            'bootstrap_servers': 'localhost:9092',
            'topic': f'raw_frames_{task_id}',
        }
        publisher = VideoStreamPublisher(
            task_id=task_id,
            kafka_config=kafka_config,
            fps=30.0,
            max_dimension=1920
        )
        try:
            if await publisher.initialize():
                publisher.is_publishing = True
                await publisher.publish_video_frames(video_path)
        except Exception as e:
            logger.error(f"在 extract_frames_and_publish 中出错: {e}")
            raise
        finally:
            await publisher.cleanup()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_async_extract_and_publish())
        else:
            asyncio.run(_async_extract_and_publish())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_extract_and_publish())
        finally:
            loop.close()
    logger.info(f"为任务 {task_id} 完成提取和发布帧")
