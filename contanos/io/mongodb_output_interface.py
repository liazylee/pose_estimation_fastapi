import asyncio
import logging
import time
from abc import ABC
from typing import Any, Dict, List

try:
    import motor.motor_asyncio
    from pymongo.errors import PyMongoError

    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False
    logging.warning("motor not installed. Please install it with: pip install motor")


class MongoDBOutput(ABC):
    """MongoDB output implementation using motor async client + asyncio.Queue for batching."""

    def __init__(self, config: Dict[str, Any]):
        if not MOTOR_AVAILABLE:
            raise ImportError("motor package is required. Install with: pip install motor")

        super().__init__()
        self.mongo_uri: str = config["mongo_uri"]
        self.database: str = config["database"]
        self.collection: str = config["collection"]

        # Batch configuration
        self.batch_size: int = config.get("batch_size", 10)
        self.batch_timeout: float = config.get("batch_timeout", 5.0)  # seconds

        self.client: motor.motor_asyncio.AsyncIOMotorClient | None = None
        self.db = None
        self.coll = None

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.get("queue_max_len", 100))
        self.is_running: bool = False
        self._producer_task: asyncio.Task | None = None

    async def initialize(self) -> bool:
        """Initialize MongoDB client and start the batch producer."""
        try:
            logging.info(f"Connecting to MongoDB at {self.mongo_uri}")

            # Create MongoDB client
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)

            # Test the connection
            await self.client.admin.command('ping')

            # Get database and collection references
            self.db = self.client[self.database]
            self.coll = self.db[self.collection]

            # Start the batch producer
            self.is_running = True
            self._producer_task = asyncio.create_task(self._batch_producer())

            logging.info(f"MongoDB output initialized for {self.database}.{self.collection}")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize MongoDB output: {e}")
            return False

    async def _batch_producer(self) -> None:
        """
        Async background task that batches documents and writes them to MongoDB.
        """
        batch: List[Dict[str, Any]] = []
        last_write_time = time.time()

        while self.is_running:
            try:
                # Try to get a document with timeout
                try:
                    document = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    batch.append(document)
                    self.queue.task_done()
                except asyncio.TimeoutError:
                    # No new documents, but check if we should flush existing batch
                    pass

                current_time = time.time()
                should_write = (
                        len(batch) >= self.batch_size or
                        (batch and (current_time - last_write_time) >= self.batch_timeout)
                )

                if should_write and batch:
                    await self._write_batch(batch)
                    batch.clear()
                    last_write_time = current_time

            except Exception as e:
                logging.error(f"Unexpected error in MongoDB batch producer: {e}")
                # Don't break the loop - continue processing

    async def _write_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Write a batch of documents to MongoDB."""
        try:
            # Use native async operation with motor
            result = await self.coll.insert_many(batch)
            logging.info(f"Inserted {len(result.inserted_ids)} documents to MongoDB")
        except PyMongoError as e:
            logging.error(f"MongoDB write error: {e}")
            # Don't raise - we want to continue processing other batches
        except Exception as e:
            logging.error(f"Unexpected error writing to MongoDB: {e}")

    async def write_data(self, results: Dict[str, Any]) -> bool:
        """Put results into the outbound queue for batching."""
        if not self.is_running:
            raise RuntimeError("MongoDB output not initialized")

        try:
            mongo_record = {
                "timestamp": results.get("timestamp", time.time()),
                "frame_id": results.get("frame_id", None),
                "task_id": results.get("task_id", None),
                "tracked_poses_results": results.get("tracked_poses_results", []),
            }

            await self.queue.put(mongo_record)
            return True
        except Exception as e:
            logging.error(f"Failed to queue data: {e}")
            # For MongoDB, we want to be resilient - log error but don't crash service
            return False

    async def cleanup(self) -> None:
        """Flush remaining batches, stop producer task, and close MongoDB client."""
        self.is_running = False

        # 1. Stop producer gracefully
        if self._producer_task:
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass

        # 2. Flush any remaining documents in queue
        remaining_batch = []
        while not self.queue.empty():
            try:
                document = self.queue.get_nowait()
                remaining_batch.append(document)
                self.queue.task_done()
            except:
                break

        if remaining_batch:
            await self._write_batch(remaining_batch)

        # 3. Close MongoDB client
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logging.error(f"Error closing MongoDB client: {e}")
            finally:
                self.client = None
                self.db = None
                self.coll = None

        logging.info("MongoDB output cleaned up")
