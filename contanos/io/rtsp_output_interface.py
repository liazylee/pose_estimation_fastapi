import asyncio
import logging
import os
import signal
import subprocess
from abc import ABC
from typing import Any, Dict

import cv2
import numpy as np


class RTSPOutput(ABC):
    """RTSP output implementation using ffmpeg subprocess + asyncio.Queue + warmup frames."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.addr: str = config["addr"]  # e.g. rtsp://127.0.0.1:8554
        self.topic: str = config["topic"]  # e.g. mystream
        self.width: int = int(config.get("width", 640))
        self.height: int = int(config.get("height", 480))
        self.fps: int = config.get("fps", 25)
        self.bitrate: str = config.get("bitrate", "1000k")
        self.codec: str = config.get("codec", "libx264")
        self.preset: str = config.get("preset", "ultrafast")
        self.pixel_format: str = config.get("pixel_format", "yuv420p")
        self.warmup_frames: int = config.get("warmup_frames", 5)  # how many black frames to send

        self.process: subprocess.Popen | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.get("queue_max_len", 5))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None

    async def _log_ffmpeg_errors(self):
        proc = self.process
        if not proc or not proc.stderr:
            return
        while True:
            line = await asyncio.to_thread(proc.stderr.readline)
            if not line:
                break
            logging.error(f"[ffmpeg] {line.decode(errors='ignore').rstrip()}")

    async def initialize(self) -> bool:
        """Start ffmpeg and warm up RTSP stream."""
        logging.info(f"Initializing RTSP stream to {self.addr}/{self.topic}")

        try:
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'rawvideo',
                '-pix_fmt', 'rgb24',
                '-s', f"{self.width}x{self.height}",
                '-r', str(self.fps),
                '-i', '-',  # stdin
                '-c:v', self.codec,
                '-preset', self.preset,
                '-tune', 'zerolatency',
                '-pix_fmt', self.pixel_format,
                '-profile:v', 'baseline',
                '-level', '3.1',
                '-g', str(self.fps),  # 1 keyframe per second
                '-keyint_min', str(self.fps),
                '-b:v', self.bitrate,
                '-f', 'rtsp',
                '-rtsp_transport', 'tcp',
                f"{self.addr}/{self.topic}"
            ]

            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                preexec_fn=os.setsid
            )

            self._stderr_task = asyncio.create_task(self._log_ffmpeg_errors())
            self.is_running = True
            self._producer_task = asyncio.create_task(self._output_producer())

            # Send warmup black frames
            await self._send_warmup_frames()

            logging.info("RTSP output initialized and warmup frames sent")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize RTSP output: {e}")
            return False

    async def _send_warmup_frames(self):
        """Send a few black frames to trigger RTSP handshake and first keyframe."""
        black_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        for _ in range(self.warmup_frames):
            await asyncio.to_thread(self._write_frame_to_ffmpeg, black_frame)
            await asyncio.sleep(1 / self.fps)

    async def _output_producer(self) -> None:
        assert self.process is not None
        while self.is_running:
            try:
                frame_np = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                if frame_np.dtype != np.uint8:
                    frame_np = frame_np.astype(np.uint8)
                if frame_np.shape[:2] != (self.height, self.width):
                    frame_np = cv2.resize(frame_np, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                if frame_np.shape[2] == 3:
                    frame_np = cv2.cvtColor(frame_np, cv2.COLOR_BGR2RGB)
                await asyncio.to_thread(self._write_frame_to_ffmpeg, frame_np)
                self.queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logging.error(f"Unexpected error in output producer: {e}")
                break

    def _write_frame_to_ffmpeg(self, frame_np: np.ndarray) -> None:
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(frame_np.tobytes())
            except BrokenPipeError:
                logging.error("FFmpeg process has terminated unexpectedly")
                self.is_running = False
            except Exception as e:
                logging.error(f"Error writing frame to ffmpeg: {e}")
                raise

    async def write_data(self, results: Dict[str, Any]) -> bool:
        if not self.is_running:
            raise RuntimeError("RTSP output not initialized")
        try:
            frame_np = results['results']['annotated_frame']
            await self.queue.put(frame_np)
            return True
        except Exception as e:
            logging.error(f"Failed to queue frame: {e}")
            raise

    async def cleanup(self) -> None:
        self.is_running = False

        for task in [self._stderr_task, self._producer_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logging.warning("FFmpeg didn't terminate, killing now")
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()

        self.process = None

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

        logging.info("RTSP output cleaned up")
