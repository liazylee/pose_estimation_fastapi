import asyncio
import datetime
import logging
import os
from abc import ABC
from typing import Any, Dict

import cv2
import numpy as np


class VideoOutput(ABC):
    """使用 OpenCV VideoWriter + asyncio.Queue 实现异步视频输出"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.task_id = config.get("task_id", "unknown")
        self.output_dir = config.get("output_dir", "output_videos")
        self.filename_template = config.get(
            "filename_template", "annotated_{task_id}_{timestamp}.mp4"
        )
        self.width: int = int(config.get("width", 1920))
        self.height: int = int(config.get("height", 1080))
        self.fps: float = float(config.get("fps", 25))
        self.fourcc_str: str = config.get("fourcc", "mp4v")
        self.process: Any = None
        self.writer: cv2.VideoWriter | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.get("queue_max_len", 100))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None
        self.output_path: str | None = None
        self.frame_count: int = 0

    async def initialize(self) -> bool:

        try:

            full_output_dir = os.path.join(self.output_dir, self.task_id)
            os.makedirs(full_output_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.filename_template.format(task_id=self.task_id, timestamp=timestamp)
            self.output_path = os.path.join(full_output_dir, filename)

            logging.info(f"Starting OpenCV video output to {self.output_path}")
            logging.info(f"Video params: {self.width}x{self.height} @ {self.fps}fps")

            # 2. FourCC
            if len(self.fourcc_str) == 4:
                fourcc = cv2.VideoWriter_fourcc(*self.fourcc_str)
            else:
                logging.warning(
                    f"Invalid fourcc '{self.fourcc_str}', fallback to 'mp4v'"
                )
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            self.writer = cv2.VideoWriter(
                self.output_path,
                fourcc,
                self.fps,
                (self.width, self.height),
                True
            )
            if not self.writer.isOpened():
                raise RuntimeError("Failed to open VideoWriter")

            self.is_running = True
            self._producer_task = asyncio.create_task(self._output_producer())

            logging.info("OpenCV video output initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize OpenCV video output: {e}")
            return False

    async def _output_producer(self) -> None:
        """

        """
        assert self.writer is not None

        async def run_in_thread(func, *args, **kwargs):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)

        while self.is_running:
            try:
                frame_np: np.ndarray = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                if frame_np.dtype != np.uint8:
                    frame_np = frame_np.astype(np.uint8)

                if frame_np.shape[:2] != (self.height, self.width):
                    frame_np = cv2.resize(
                        frame_np, (self.width, self.height), interpolation=cv2.INTER_LINEAR
                    )

                await run_in_thread(self.writer.write, frame_np)

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

        if self._producer_task:
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        if self.writer:
            await asyncio.get_running_loop().run_in_executor(None, self.writer.release)
            self.writer = None

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

        if self.output_path and os.path.exists(self.output_path):
            file_size = os.path.getsize(self.output_path)
            logging.info(
                f"Video saved: {self.output_path} "
                f"({file_size:,} bytes, {self.frame_count} frames)"
            )
        else:
            logging.error("Video file was not created or path is invalid")

        logging.info("OpenCV video output cleaned up")
