import asyncio
import logging
import os
import subprocess
from abc import ABC
from typing import Any, Dict

import numpy as np


class VideoOutput(ABC):
    """使用 FFmpeg + asyncio.Queue 实现异步视频输出"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.task_id = config.get("task_id", "unknown")
        self.output_dir = config.get("output_dir", "output_videos")
        self.filename_template = config.get(
            "filename_template", "annotated_{task_id}.mp4"
        )
        self.width: int = int(config.get("width", 1920))
        self.height: int = int(config.get("height", 1080))
        self.fps: float = float(config.get("fps", 25))
        self.codec: str = config.get("codec", "h264")
        self.preset: str = config.get("preset", "fast")
        self.crf: int = int(config.get("crf", 23))
        self.bitrate: str = config.get("bitrate", "4000k")
        self.pixel_format: str = config.get("pixel_format", "yuv420p")

        self.process: subprocess.Popen | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.get("queue_max_len", 100))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None
        self.output_path: str | None = None
        self.frame_count: int = 0

    async def initialize(self) -> bool:
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            filename = self.filename_template.format(task_id=self.task_id)
            self.output_path = os.path.join(self.output_dir, filename)

            logging.info(f"Starting FFmpeg video output to {self.output_path}")
            logging.info(f"Video params: {self.width}x{self.height} @ {self.fps}fps")

            # 构建FFmpeg命令
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "rawvideo",  # 输入格式
                "-vcodec", "rawvideo",
                "-s", f"{self.width}x{self.height}",  # 输入尺寸
                "-pix_fmt", "bgr24",  # OpenCV使用BGR格式
                "-r", str(self.fps),  # 输入帧率
                "-i", "-",  # 从stdin读取
                "-c:v", "libx264",  # 使用H.264编码器
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-pix_fmt", self.pixel_format,
                "-r", str(self.fps),  # 输出帧率
                self.output_path
            ]

            # 如果指定了bitrate，添加bitrate参数（与CRF互斥）
            if hasattr(self, 'use_bitrate') and self.use_bitrate:
                # 移除CRF，使用bitrate
                cmd_idx = ffmpeg_cmd.index('-crf')
                ffmpeg_cmd[cmd_idx:cmd_idx + 2] = ['-b:v', self.bitrate]

            logging.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")

            # 启动FFmpeg进程
            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )

            self.is_running = True
            self._producer_task = asyncio.create_task(self._output_producer())

            logging.info("FFmpeg video output initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize FFmpeg video output: {e}")
            return False

    async def _output_producer(self) -> None:
        """异步处理帧数据并发送给FFmpeg"""
        assert self.process is not None

        async def write_frame_to_ffmpeg(frame_bytes: bytes):
            """异步写入帧数据到FFmpeg"""
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                self.process.stdin.write,
                frame_bytes
            )

        while self.is_running:
            try:
                frame_np: np.ndarray = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # 确保数据类型正确
                if frame_np.dtype != np.uint8:
                    frame_np = frame_np.astype(np.uint8)

                # 确保尺寸正确
                if frame_np.shape[:2] != (self.height, self.width):
                    import cv2
                    frame_np = cv2.resize(
                        frame_np, (self.width, self.height),
                        interpolation=cv2.INTER_LINEAR
                    )

                # 转换为字节并写入FFmpeg
                frame_bytes = frame_np.tobytes()
                await write_frame_to_ffmpeg(frame_bytes)

                self.frame_count += 1
                if self.frame_count % 100 == 0:
                    logging.info(f"Written {self.frame_count} frames")

                self.queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Error in video producer: {e}")
                break

    async def write_data(self, results: Dict[str, Any]) -> bool:
        if not self.is_running:
            raise RuntimeError("Video output not initialized")

        try:
            frame_np = results["results"]["annotated_frame"]
            await self.queue.put(frame_np)
            return True
        except Exception as e:
            logging.error(f"Failed to queue frame: {e}")
            raise

    async def cleanup(self) -> None:
        self.is_running = False

        # 取消生产者任务
        if self._producer_task:
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        # 关闭FFmpeg进程
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()

            # 等待进程结束
            try:
                stdout, stderr = await asyncio.get_running_loop().run_in_executor(
                    None, self.process.communicate
                )
                if stderr:
                    logging.info(f"FFmpeg stderr: {stderr.decode()}")
            except Exception as e:
                logging.error(f"Error during FFmpeg cleanup: {e}")

            self.process = None

        # 清空队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

        # 检查输出文件
        if self.output_path and os.path.exists(self.output_path):
            file_size = os.path.getsize(self.output_path)
            logging.info(
                f"Video saved: {self.output_path} "
                f"({file_size:,} bytes, {self.frame_count} frames)"
            )
        else:
            logging.error("Video file was not created or path is invalid")

        logging.info("FFmpeg video output cleaned up")
