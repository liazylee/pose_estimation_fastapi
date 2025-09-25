import asyncio
import asyncio.subprocess
import json
import logging
import time
from abc import ABC
from asyncio import Queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import numpy as np

from contanos.utils.serializers import encode_frame_to_base64
from contanos.metrics.prometheus import (
    MetricsLabelContext,
    service_decode_errors_total,
    service_input_queue_size,
    service_messages_consumed_total,
)

logger = logging.getLogger(__name__)
try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    from kafka.consumer.fetcher import ConsumerRecord

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("kafka-python not installed. Please install it with: pip install kafka-python")


class KafkaInput(ABC):
    """Kafka message input implementation using asyncio.Queue and kafka-python."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        metrics_service: Optional[str] = None,
        metrics_task_id: Optional[str] = None,
        metrics_worker_id: Optional[str] = None,
        metrics_topic: Optional[str] = None,
    ):
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python package is required. Install with: pip install kafka-python")

        super().__init__()
        self.bootstrap_servers = config["bootstrap_servers"]
        self.topic = config['topic']
        self.group_id = config.get('group_id', f"kafka_input_{int(time.time())}")
        self.auto_offset_reset = config.get('auto_offset_reset', 'latest')
        self.max_poll_records = config.get('max_poll_records', 1)
        self.consumer_timeout_ms = config.get('consumer_timeout_ms', 10)
        self.enable_auto_commit = config.get('enable_auto_commit', True)

        # Enhanced asyncio constructs with backpressure support
        queue_size = config.get('message_queue_size', 1000)
        self.message_queue: Queue = Queue(maxsize=queue_size)
        self._executor = ThreadPoolExecutor(max_workers=config.get('max_workers', 1),
                                            thread_name_prefix=f"kafka_{self.group_id}")

        # Backpressure management
        self._backpressure_threshold = int(queue_size * 0.8)  # 80% threshold
        self._backpressure_active = False
        self._backpressure_delay_ms = config.get('backpressure_delay_ms', 100)
        self._queue_high_watermark = int(queue_size * 0.9)  # 90% high watermark
        self._loop: asyncio.AbstractEventLoop | None = None

        # Kafka consumer
        self.consumer = None
        self.is_running = False
        self._consumer_task = None

        default_task = metrics_task_id or config.get('task_id') or 'default_task'
        worker_label = str(metrics_worker_id) if metrics_worker_id is not None else 'input'
        topic_label = metrics_topic or self.topic
        service_label = metrics_service or 'unknown'
        self._metrics_context = MetricsLabelContext(
            service=service_label,
            worker_id=worker_label,
            topic=topic_label,
            initial_task_id=default_task,
        )
        self._default_task_id = default_task

    def _record_queue_enqueue(self, task_id: Optional[str], count: int = 1) -> None:
        labels = self._metrics_context.labels_for(task_id)
        if count:
            service_messages_consumed_total.labels(**labels).inc(count)
        service_input_queue_size.labels(**labels).set(self.message_queue.qsize())

    def _update_queue_size(self, task_id: Optional[str] = None) -> None:
        labels = self._metrics_context.labels_for(task_id)
        service_input_queue_size.labels(**labels).set(self.message_queue.qsize())

    def _record_decode_error(self, task_id: Optional[str] = None) -> None:
        labels = self._metrics_context.labels_for(task_id)
        service_decode_errors_total.labels(**labels).inc()

    # initialize the Kafka consumer and start the background loop
    async def initialize(self) -> bool:
        """Initialize Kafka connection and start background loop."""
        try:
            self._loop = asyncio.get_running_loop()

            logger.info(f"Starting Kafka consumer for servers {self.bootstrap_servers}")

            # Create consumer
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                max_poll_records=self.max_poll_records,
                consumer_timeout_ms=self.consumer_timeout_ms,
                enable_auto_commit=self.enable_auto_commit,
                key_deserializer=lambda k: k.decode('utf-8') if k else None,
                value_deserializer=lambda v: v)

            # Start consumer task
            self.is_running = True
            self._consumer_task = asyncio.create_task(self._consume_messages())

            logger.info(f"Kafka connection established, subscribed to topic: {self.topic}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Kafka input: {e}")
            return False

    # kafka consumer background task to poll messages and process them
    async def _consume_messages(self):
        """Background task to consume messages from Kafka."""
        while self.is_running:
            try:
                # Run blocking poll in executor
                messages = await self._loop.run_in_executor(
                    self._executor,
                    lambda: self.consumer.poll(timeout_ms=self.consumer_timeout_ms)
                )
                if not messages:
                    continue
                for tp, message in messages.items():
                    for record in message:
                        #
                        await self._process_record(record)

            except Exception as e:
                logger.error(f"Error consuming Kafka messages: {e}")
                await asyncio.sleep(1)

    async def _process_record(self, record: ConsumerRecord):
        """
        Process a single Kafka record and queue it for further processing.
        """
        try:
            message_str = record.value.decode('utf-8')
            message = json.loads(message_str)
            if isinstance(message, dict) and 'frame_id' in message:
                task_id = message.get('task_id', self._default_task_id)
                message.setdefault('task_id', task_id)
                # Quick check: if queue is too full, apply light backpressure
                if self.message_queue.qsize() >= self._backpressure_threshold:
                    await asyncio.sleep(0.01)  # Light delay
                await self.message_queue.put(message)
                self._record_queue_enqueue(task_id)
                return
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._record_decode_error()

        start_frame_id_str = record.key
        if not start_frame_id_str:
            logger.warning("Binary message received without a key (start_frame_id). Skipping.")
            return

        try:
            key_dict = json.loads(record.key)
            frame_id_start = int(key_dict.get('frame_id_start', 0))
            width = int(key_dict.get('width', 640))
            height = int(key_dict.get('height', 480))
            channels = int(key_dict.get('channels', 3))
            fps = int(key_dict.get('fps', 30))

            task_id = key_dict.get('task_id', self._default_task_id)
            await self._decode_and_queue_frames(
                video_segment_bytes=record.value,
                frame_id_start=frame_id_start,
                width=width,
                height=height,
                channels=channels,
                fps=fps,
                task_id=task_id,
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing Kafka key: {e}")
            logger.warning(f"Could not parse start_frame_id from Kafka key: '{start_frame_id_str}'.")
        except Exception as e:
            logger.error(f"Error submitting decoding task for start_frame_id {start_frame_id_str}: {e}")

    async def _decode_and_queue_frames(
            self,
            video_segment_bytes: bytes,
            frame_id_start: int,
            width: int,
            height: int,
            channels: int = 3,
            fps: float = 30.0,
            task_id: Optional[str] = None,
    ):
        """
        Decode video segment and enqueue base64 JPEG frames with metadata.
        """
        pix_fmt = "bgr24"
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            pix_fmt,
            "pipe:1",
        ]

        proc = await asyncio.subprocess.create_subprocess_exec(
            *ffmpeg_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_data, stderr_data = await proc.communicate(input=video_segment_bytes)
        if proc.returncode != 0:
            logger.error(
                f"FFmpeg decode failed (start={frame_id_start}), code={proc.returncode}, "
                f"stderr={stderr_data.decode(errors='ignore')}"
            )
            self._record_decode_error(task_id)
            return

        frame_size = width * height * channels
        total_bytes = len(stdout_data)
        remainder = total_bytes % frame_size
        if remainder:
            logger.warning(
                f"Segment start={frame_id_start} has {remainder} extra bytes; "
                f"discarding truncated tail frame."
            )
            total_bytes -= remainder

        total_frames = total_bytes // frame_size
        if total_frames == 0:
            logger.warning(f"Segment start={frame_id_start} produced 0 full frames — skip.")
            return
        segment_base_ts = time.time()  # Unix 秒
        nanos_per_frame = 1e9 / fps
        res = []
        for idx in range(total_frames):
            offset = idx * frame_size
            chunk = stdout_data[offset: offset + frame_size]

            frame_np = np.frombuffer(chunk, dtype=np.uint8).reshape((height, width, channels))
            b64_bytes = encode_frame_to_base64(frame_np, quality=85)

            frame_id = frame_id_start + idx

            # Calculate timestamp in ISO 8601 format
            ts_ns = int(segment_base_ts * 1e9 + idx * nanos_per_frame)
            ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts_ns / 1e9))
            ts_iso += f".{ts_ns % 1_000_000_000:09d}Z"

            message_task_id = task_id or self._default_task_id
            message = {
                "task_id": message_task_id,
                "frame_id": frame_id,
                "timestamp": ts_iso,
                "image_format": "jpeg",
                "image_bytes": b64_bytes,
            }

            res.append(frame_id)
            # Light backpressure check only when queue is very full
            if self.message_queue.qsize() >= self._queue_high_watermark:
                await asyncio.sleep(0.001)  # Minimal delay
            await self.message_queue.put(message)
            self._record_queue_enqueue(message_task_id)
        # sleep a bit to yield control
        await asyncio.sleep(0.5)
        if len(res) != total_frames:
            logger.error(f'the frame is not ordered')
        # logger.info(
        #     f"Decoded {total_frames} frames (frame_id {frame_id_start} "
        #     f"→ {frame_id_start + total_frames - 1})"
        # )

    async def read_data(self) -> Optional[Dict[str, Any]]:
        """Read message from queue."""
        if not self.is_running:
            raise Exception("Kafka input not initialized or stopped")
        message = None
        try:
            message = await asyncio.wait_for(self.message_queue.get(), timeout=self.consumer_timeout_ms)
            return message
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for Kafka message")
            return None
        except asyncio.CancelledError:
            logger.info("Kafka input read_data task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error reading Kafka message: {e}")
            raise
        finally:
            if message is not None:
                self.message_queue.task_done()
                self._update_queue_size(message.get('task_id'))

    async def _handle_backpressure(self):
        """Handle backpressure when queue is getting full."""
        current_size = self.message_queue.qsize()

        if current_size >= self._queue_high_watermark:
            if not self._backpressure_active:
                self._backpressure_active = True
                logger.warning(
                    f"[BACKPRESSURE] Queue pressure HIGH: {current_size}/{self.message_queue.maxsize}. Activating backpressure.")

            # Apply exponential backoff based on queue fullness
            pressure_ratio = current_size / self.message_queue.maxsize
            delay_ms = self._backpressure_delay_ms * (1 + pressure_ratio)
            await asyncio.sleep(delay_ms / 1000.0)

        elif current_size < self._backpressure_threshold and self._backpressure_active:
            self._backpressure_active = False
            logger.info(
                f"[BACKPRESSURE] Queue pressure NORMAL: {current_size}/{self.message_queue.maxsize}. Deactivating backpressure.")

    async def _handle_backpressure_for_frame_queue(self):
        """Lightweight backpressure check for frame queuing."""
        if self.message_queue.qsize() >= self._queue_high_watermark:
            # Small delay to prevent overwhelming the queue
            await asyncio.sleep(0.01)

    async def cleanup(self):
        """Clean up Kafka resources."""
        self.is_running = False
        # Stop consumer early to break poll()
        if self.consumer:
            try:
                await self._loop.run_in_executor(self._executor, self.consumer.close)
            except KafkaError as e:
                logger.error(f"Error closing Kafka consumer: {e}")
        # Cancel consumer task
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                logger.info("Kafka consumer task cancelled")

        # Shutdown executor
        self._executor.shutdown(wait=True)

        # Clear queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
                self.message_queue.task_done()
            except asyncio.QueueEmpty:
                break

        self._update_queue_size()
        logger.info("Kafka input cleaned up")

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status for monitoring."""
        current_size = self.message_queue.qsize()
        max_size = self.message_queue.maxsize

        return {
            'current_size': current_size,
            'max_size': max_size,
            'usage_percent': (current_size / max_size) * 100 if max_size > 0 else 0,
            'backpressure_active': self._backpressure_active,
            'backpressure_threshold': self._backpressure_threshold,
            'high_watermark': self._queue_high_watermark,
            'topic': self.topic,
            'group_id': self.group_id
        }
