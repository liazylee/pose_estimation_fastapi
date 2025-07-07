import asyncio
import json
import logging
import time
import uuid
from abc import ABC
from asyncio import Queue
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logging.warning("kafka-python not installed. Please install it with: pip install kafka-python")


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
        self.message_queue: Queue = Queue(maxsize=config.get('message_queue_size', 100))
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

            logging.info(f"Starting Kafka consumer for servers {self.bootstrap_servers}")

            # Create consumer
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                max_poll_records=self.max_poll_records,
                consumer_timeout_ms=self.consumer_timeout_ms,
                enable_auto_commit=self.enable_auto_commit,
                value_deserializer=lambda x: x.decode('utf-8') if x else None
            )

            # Start consumer task
            self.is_running = True
            self._consumer_task = asyncio.create_task(self._consume_messages())

            logging.info(f"Kafka connection established, subscribed to topic: {self.topic}")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize Kafka input: {e}")
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

                if messages:
                    for topic_partition, records in messages.items():
                        for record in records:
                            await self._process_and_queue(record)

            except Exception as e:
                logging.error(f"Error consuming Kafka messages: {e}")
                await asyncio.sleep(1)

    async def _process_and_queue(self, record):
        """Process and queue a Kafka message."""
        try:
            # Process message in executor
            message = await self._loop.run_in_executor(self._executor, self._process_message, record)
            if message is not None:
                await self.message_queue.put(message)
                logging.debug(f"Pushed message to queue: {message.get('frame_id_str', 'unknown')}")
        except Exception as e:
            logging.error(f"Error queuing Kafka message: {e}")

    def _process_message(self, record) -> Optional[Dict[str, Any]]:
        """
        """
        try:
            message = json.loads(record.value)
            if not isinstance(message, dict):
                raise ValueError("Kafka message must be a JSON object")
            if message.get('frame_id_str') is None:
                pass
        except ValueError as e:
            logging.error(f"Invalid Kafka message format: {e}")
            return None

    async def read_data(self) -> Optional[Dict[str, Any]]:
        """Read message from queue."""
        if not self.is_running:
            raise Exception("Kafka input not initialized or stopped")

        try:
            message = await asyncio.wait_for(self.message_queue.get(), timeout=5.0)

        except asyncio.TimeoutError:
            logging.warning("Timeout waiting for Kafka message")
            return None
        except asyncio.CancelledError:
            logging.info("Kafka input read_data task cancelled")
            return None
        except Exception as e:
            logging.error(f"Error reading Kafka message: {e}")
            return None
        return message

    async def cleanup(self):
        """Clean up Kafka resources."""
        self.is_running = False

        # Cancel consumer task
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Close consumer
        if self.consumer:
            try:
                await self._loop.run_in_executor(self._executor, self.consumer.close)
            except Exception as e:
                logging.error(f"Error closing Kafka consumer: {e}")

        # Shutdown executor
        self._executor.shutdown(wait=True)

        # Clear queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
                self.message_queue.task_done()
            except asyncio.QueueEmpty:
                break

        logging.info("Kafka input cleaned up")
