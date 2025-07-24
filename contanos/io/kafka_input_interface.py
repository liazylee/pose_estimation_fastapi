import asyncio
import json
import logging
import time
import uuid
from abc import ABC
from asyncio import Queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import numpy as np

from contanos.utils.serializers import encode_frame_to_base64

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

    def __init__(self, config: Dict[str, Any]):
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python package is required. Install with: pip install kafka-python")

        super().__init__()
        self.bootstrap_servers = config["bootstrap_servers"]
        self.topic = config['topic']
        self.group_id = config.get('group_id', f"kafka_input_{int(time.time())}")
        unique_suffix = str(uuid.uuid4())[:8]  # Add unique suffix
        self.group_id = f"{self.group_id}_{unique_suffix}"
        self.auto_offset_reset = config.get('auto_offset_reset', 'latest')
        self.max_poll_records = config.get('max_poll_records', 1)
        self.consumer_timeout_ms = config.get('consumer_timeout_ms', 1000)
        self.enable_auto_commit = config.get('enable_auto_commit', True)

        # Asyncio constructs
        self.message_queue: Queue = Queue(maxsize=config.get('message_queue_size', 1000))
        self.consumer = KafkaConsumer()
        self._executor = ThreadPoolExecutor(max_workers=config.get('max_workers', 1),
                                            thread_name_prefix=f"kafka_{self.group_id}")
        self._loop: asyncio.AbstractEventLoop | None = None

        # Kafka consumer
        self.consumer = None
        self.is_running = False
        self._consumer_task = None

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
                await self.message_queue.put(message)
                return
        except(UnicodeDecodeError, json.JSONDecodeError):
            logger.info(f'failed to decode message as json string , try to  decode as bytes')
            pass

        start_frame_id_str = record.key
        if not start_frame_id_str:
            logger.warning("Binary message received without a key (start_frame_id). Skipping.")
            return

        try:
            key_dict = json.loads(record.key)
            start_frame_id_str = int(key_dict.get('start_frame_id', 0))
            width = int(key_dict.get('width', 640))
            height = int(key_dict.get('height', 480))
            channels = int(key_dict.get('channels', 3))
            fps = int(key_dict.get('fps', 30))
            # Submit decoding task to executor
            await self._loop.run_in_executor(
                self._executor,
                self._decode_and_queue_frames,
                record.value,
                start_frame_id_str,
                width,
                height,
                channels,
                fps

            )
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing Kafka key: {e}")
            logger.warning(f"Could not parse start_frame_id from Kafka key: '{start_frame_id_str}'.")
        except Exception as e:
            logger.error(f"Error submitting decoding task for start_frame_id {start_frame_id_str}: {e}")

    def _decode_and_queue_frames(self,
                                 video_segment_bytes: bytes,
                                 frame_id_start: int,
                                 width: int,
                                 height: int,
                                 channels: int = 3,
                                 fps: float = 30.0):
        """
        Decode video segment and enqueue base64 JPEG frames with metadata.
        """
        frame_size = width * height * channels
        pix_fmt = 'bgr24'

        ffmpeg_cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error',
            '-i', 'pipe:0',
            '-f', 'rawvideo',
            '-pix_fmt', pix_fmt,
            'pipe:1'
        ]

        import subprocess
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        try:
            stdout_data, _ = proc.communicate(input=video_segment_bytes)
        except Exception as e:
            logger.error(f"FFmpeg decode failed at frame {frame_id_start}: {e}")
            return

        frame_index = 0
        for i in range(0, len(stdout_data), frame_size):
            chunk = stdout_data[i: i + frame_size]
            if len(chunk) != frame_size:
                continue

            frame_np = np.frombuffer(chunk, dtype=np.uint8).reshape((height, width, channels))
            b64_bytes = encode_frame_to_base64(frame_np, quality=85)
            frame_id = frame_id_start + frame_index
            timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.', time.gmtime()) + f"{int(time.time() % 1 * 1e6):06}Z"

            message = {
                "task_id": "default_task",
                "frame_id": frame_id,
                "timestamp": timestamp,
                "image_format": "jpeg",
                "image_bytes": b64_bytes
            }
            # logger.info(f'frame_id = {frame_id}')
            asyncio.run_coroutine_threadsafe(self.message_queue.put(message), self._loop)
            # logger.info(f'self.message_queue.qsize() = {self.message_queue.qsize()}')
            frame_index += 1

        logger.info(f"Decoded {frame_index} frames starting from frame {frame_id_start}")

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
            raise
        except asyncio.CancelledError:
            logger.info("Kafka input read_data task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error reading Kafka message: {e}")
            raise
        finally:
            if message is not None:
                self.message_queue.task_done()

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

        logger.info("Kafka input cleaned up")
