import asyncio
import functools
import logging
import subprocess
import os
from abc import ABC
from typing import Any, Dict
import datetime

import cv2
import numpy as np


class VideoOutput(ABC):
    """Video file output implementation using ffmpeg subprocess + asyncio.Queue."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.task_id = config.get("task_id", "unknown")
        self.output_dir = config.get("output_dir", "output_videos")
        self.filename_template = config.get("filename_template", "annotated_{task_id}_{timestamp}.mp4")
        self.width: int = int(config.get("width", 1920))
        self.height: int = int(config.get("height", 1080))
        self.fps: int = config.get("fps", 25)
        self.bitrate: str = config.get("bitrate", "2000k")
        self.codec: str = config.get("codec", "libx264")
        self.preset: str = config.get("preset", "fast")
        self.pixel_format: str = config.get("pixel_format", "yuv420p")
        self.crf: int = config.get("crf", 23)  # Constant Rate Factor for quality

        self.process: subprocess.Popen | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.get("queue_max_len", 100))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None
        self.output_path: str | None = None
        self.frame_count: int = 0

    async def initialize(self) -> bool:
        """Configure and start the ffmpeg process for video file output."""
        try:
            # Create output directory
            full_output_dir = os.path.join(self.output_dir, self.task_id)
            os.makedirs(full_output_dir, exist_ok=True)

            # Generate output filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.filename_template.format(task_id=self.task_id, timestamp=timestamp)
            self.output_path = os.path.join(full_output_dir, filename)

            logging.info(f"Starting video output to {self.output_path}")
            logging.info(f"Video parameters: {self.width}x{self.height} @ {self.fps}fps")
            logging.info(f"Codec: {self.codec}, preset: {self.preset}, CRF: {self.crf}")

            # Build ffmpeg command for high-quality MP4 output
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'rgb24',
                '-s', f"{self.width}x{self.height}",
                '-r', str(self.fps),
                '-i', '-',  # input from stdin
                '-c:v', self.codec,
                '-preset', self.preset,
                '-crf', str(self.crf),
                '-pix_fmt', self.pixel_format,
                '-movflags', '+faststart',  # Optimize for web playback
                '-avoid_negative_ts', 'make_zero',
                self.output_path
            ]

            logging.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")

            # Start ffmpeg process
            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )

            # Start the async producer
            self.is_running = True
            self._producer_task = asyncio.create_task(self._output_producer())

            logging.info("Video output initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize video output: {e}")
            return False

    async def _output_producer(self) -> None:
        """
        Async background task:
        • Waits for frame data in `self.queue`
        • Writes frames to ffmpeg stdin in a worker thread
        """
        assert self.process is not None

        while self.is_running:
            try:
                frame_np = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Ensure frame is in correct format (RGB24)
                if frame_np.dtype != np.uint8:
                    frame_np = frame_np.astype(np.uint8)

                # Ensure frame has correct dimensions
                if frame_np.shape[:2] != (self.height, self.width):
                    frame_np = cv2.resize(frame_np, (self.width, self.height), interpolation=cv2.INTER_LINEAR)

                # Ensure frame is RGB (convert from BGR if needed)
                if frame_np.shape[2] == 3:
                    # Assume input is BGR, convert to RGB for ffmpeg
                    frame_np = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)

                async def run_in_thread(func, *args, **kwargs):
                    loop = asyncio.get_running_loop()
                    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

                # Write frame to ffmpeg in background thread
                await run_in_thread(self._write_frame_to_ffmpeg, frame_np)

                self.frame_count += 1
                if self.frame_count % 100 == 0:
                    logging.info(f"Written {self.frame_count} frames to video")

                self.queue.task_done()

            except asyncio.TimeoutError:
                continue  # idle loop – no frame yet
            except Exception as e:
                logging.error(f"Unexpected error in video output producer: {e}")
                break

    def _write_frame_to_ffmpeg(self, frame_np: np.ndarray) -> None:
        """Write a single frame to ffmpeg stdin (blocking operation)."""
        if self.process and self.process.stdin:
            try:
                frame_bytes = frame_np.tobytes()
                self.process.stdin.write(frame_bytes)
                self.process.stdin.flush()
            except BrokenPipeError:
                logging.error("FFmpeg process has terminated unexpectedly")
                self.is_running = False
            except Exception as e:
                logging.error(f"Error writing frame to ffmpeg: {e}")
                raise

    async def write_data(self, results: Dict[str, Any]) -> bool:
        """Put a frame into the outbound queue."""
        if not self.is_running:
            raise RuntimeError("Video output not initialized")

        try:
            frame_np = results['results']['annotated_frame']
            await self.queue.put(frame_np)
            return True
        except Exception as e:
            logging.error(f"Failed to queue frame for video: {e}")
            raise RuntimeError(f"Failed to write video frame: {e}") from e

    async def cleanup(self) -> None:
        """Flush queue, stop producer task, and terminate ffmpeg process."""
        self.is_running = False

        # 1. Stop producer gracefully
        if self._producer_task:
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        # 2. Close ffmpeg stdin and terminate process
        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()

                # Wait for process to terminate with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(self.process.wait),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logging.warning("FFmpeg process didn't terminate gracefully, killing it")
                    self.process.kill()
                    await asyncio.to_thread(self.process.wait)

            except Exception as e:
                logging.error(f"Error during ffmpeg cleanup: {e}")
            finally:
                self.process = None

        # 3. Drain queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except:
                break

        # 4. Check final video file
        if self.output_path and os.path.exists(self.output_path):
            file_size = os.path.getsize(self.output_path)
            logging.info(f"Video output completed: {self.output_path} ({file_size:,} bytes, {self.frame_count} frames)")
            
            if file_size > 1024:  # At least 1KB
                logging.info("Video file appears to be valid and should be playable")
            else:
                logging.warning("Video file may be corrupted (very small size)")
        else:
            logging.error(f"Video file was not created: {self.output_path}")

        logging.info("Video output cleaned up") 