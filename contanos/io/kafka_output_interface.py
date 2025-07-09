from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC
from typing import Any, Dict

try:
    from kafka import KafkaProducer
    from kafka.errors import KafkaError

    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logging.warning("kafka-python not installed. Please install it with: pip install kafka-python")


class KafkaOutput(ABC):
    """Kafka output implementation using kafka-python producer + asyncio.Queue."""

    def __init__(self, config: Dict[str, Any]):
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python package is required. Install with: pip install kafka-python")

        super().__init__()
        self.bootstrap_servers = config["bootstrap_servers"]
        self.topic: str = config["topic"]

        # Kafka producer configuration
        self.acks = config.get('acks', 'all')
        self.retries = config.get('retries', 3)
        self.batch_size = config.get('batch_size', 16384)
        self.linger_ms = config.get('linger_ms', 10)
        self.buffer_memory = config.get('buffer_memory', 33554432)
        self.compression_type = config.get('compression_type', 'gzip')

        self.producer: KafkaProducer | None = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=int(config.get("queue_max_len", 100)))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None

    async def initialize(self) -> bool:
        """
        Configure and connect the Kafka producer.
        """
        try:
            logging.info(f"Connecting to Kafka servers {self.bootstrap_servers}")

            # Build the producer
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                acks=self.acks,
                retries=self.retries,
                batch_size=self.batch_size,
                linger_ms=self.linger_ms,
                buffer_memory=self.buffer_memory,
                compression_type=self.compression_type,
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
            )

            # Start the async producer
            self.is_running = True
            self._producer_task = asyncio.create_task(self._output_producer())

            logging.info("Kafka output initialised")
            return True

        except Exception as e:
            logging.error(f"Failed to initialise Kafka output: {e}")
            return False

    async def _output_producer(self) -> None:
        """
        Async background task:
        • Waits for items in `self.queue`
        • Sends them via kafka producer
        """
        assert self.producer is not None

        while self.is_running:
            try:
                results = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Send message via Kafka producer (run in executor to avoid blocking)
                loop = asyncio.get_running_loop()
                future = await loop.run_in_executor(
                    None,
                    lambda: self.producer.send(self.topic, value=results)
                )

                # Optionally wait for send confirmation
                # await loop.run_in_executor(None, future.get, 10)  # 10 second timeout

                logging.debug(f"Published to {self.topic}: {results.get('frame_id', 'unknown')}")
                self.queue.task_done()

            except asyncio.TimeoutError:
                continue  # idle loop – no message yet
            except Exception as e:
                logging.error(f"Unexpected error in output producer: {e}")

    async def write_data(self, results: Dict[str, Any]) -> bool:
        """Put results into the outbound queue."""
        if not self.is_running:
            raise RuntimeError("Kafka output not initialised")

        try:
            # Add timestamp if not present
            if 'timestamp' not in results:
                results['timestamp'] = time.time()

            await self.queue.put(results)
            return True
        except Exception as e:
            logging.error(f"Failed to queue data: {e}")
            raise RuntimeError(f"Failed to write Kafka data: {e}") from e

    async def cleanup(self) -> None:
        """Flush queue, stop producer task, and close the Kafka producer."""
        self.is_running = False

        # 1. Stop producer gracefully
        if self._producer_task:
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        # 2. Flush and close Kafka producer
        if self.producer:
            try:
                # Flush any pending messages
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.producer.flush, 10)  # 10 second timeout
                await loop.run_in_executor(None, self.producer.close, 10)  # 10 second timeout
            except Exception as e:
                logging.error(f"Error closing Kafka producer: {e}")
            finally:
                self.producer = None

        # 3. Drain queue
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()

        logging.info("Kafka output cleaned up")
