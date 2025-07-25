import asyncio
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Dict


class MultiInputInterface:
    """Wrapper for multiple input interfaces with synchronized multi-entry queue."""

    def __init__(self, interfaces: List[Any], frame_timeout_sec: float = 20):
        self.interfaces = interfaces
        self.is_running = False
        self._executor = ThreadPoolExecutor(max_workers=len(interfaces))
        self._producer_tasks = []
        self._data_dict = defaultdict(lambda: {})  # {frame_id: {interface_idx: data}}
        self._queue = asyncio.Queue(maxsize=10000)  # Stores completed {interface_idx: data}
        self._frame_timestamp_dict = {}
        self._lock = asyncio.Lock()  # Protects _data_dict and _queue
        self._num_interfaces = len(interfaces)
        self.max_pending_frames = 10000
        self._frame_id_order = []  #
        self.frame_timeout_sec = frame_timeout_sec

    async def initialize(self) -> bool:
        """Initialize all input interfaces and start producers."""
        try:
            # Initialize all interfaces concurrently
            results = await asyncio.gather(
                *[interface.initialize() for interface in self.interfaces],
                return_exceptions=True
            )
            if not all(results):
                logging.error("One or more interfaces failed to initialize")
                return False

            self.is_running = True
            # Start producer tasks for each interface
            for idx, interface in enumerate(self.interfaces):
                task = asyncio.create_task(self._interface_producer(idx, interface))
                self._producer_tasks.append(task)

            logging.info("MultiInputInterface initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize MultiInputInterface: {e}")
            return False

    async def _interface_producer(self, interface_idx, interface):
        """Background task to fetch data from an interface and update dictionary."""
        while self.is_running:
            try:
                data = await interface.read_data()

                if data is None:
                    logging.warning(f"Interface {interface_idx} returned None, skipping")
                    continue
                frame_id = data.get('frame_id')
                if frame_id is None:
                    logging.warning(f"Interface {interface_idx} provided no frame_id, skipping")
                    continue

                async with self._lock:
                    # Add new frame_id if not already present
                    if frame_id not in self._data_dict:
                        self._frame_id_order.append(frame_id)

                    self._data_dict[frame_id][interface_idx] = data

                    # If buffer too large, drop oldest
                    if len(self._frame_id_order) > self.max_pending_frames:
                        old_frame_id = self._frame_id_order.pop(0)
                        if old_frame_id in self._data_dict:
                            del self._data_dict[old_frame_id]
                            logging.warning(f"Dropped frame {old_frame_id} due to pending overflow")

                    # If this frame is now complete
                    if len(self._data_dict[frame_id]) == self._num_interfaces:
                        await self._queue.put(self._data_dict[frame_id])
                        del self._data_dict[frame_id]
                        self._frame_id_order.remove(frame_id)
                        logging.debug(f"Synchronized frame {frame_id} with {self._num_interfaces} interfaces")
                    else:
                        # 记录当前帧的同步状态
                        missing_interfaces = [i for i in range(self._num_interfaces) if i not in self._data_dict[frame_id]]
                        logging.debug(f"Frame {frame_id} waiting for interfaces: {missing_interfaces}")
                        
            except Exception as e:
                logging.error(f"Interface {interface_idx} error: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on error

    async def read_data(self) -> Dict[str, Any]:
        """Read synchronized data for a frame_id from the queue."""
        if not self.is_running:
            raise Exception("MultiInputInterface not initialized or stopped")

        try:
            frame_data = await asyncio.wait_for(self._queue.get(), timeout=self.frame_timeout_sec)
            self._queue.task_done()

            merged = {}
            for idx in sorted(frame_data.keys()):
                part = frame_data[idx]
                if not isinstance(part, dict):
                    logging.warning(f"Data from interface {idx} is not a dict: {part}")
                    continue
                merged.update(part)  # simple merge, later keys overwrite earlier ones if conflict

            return merged
        except asyncio.TimeoutError:
            # 添加更详细的超时信息
            pending_frames = len(self._frame_id_order)
            logging.warning(f"Timeout waiting for synchronized data. Pending frames: {pending_frames}")
            if pending_frames > 0:
                logging.warning(f"Oldest pending frame: {self._frame_id_order[0] if self._frame_id_order else 'None'}")
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise Exception(f"Failed to read synchronized data: {e}")

    async def cleanup(self):
        """Clean up all interfaces and resources."""
        self.is_running = False

        await asyncio.gather(
            *[interface.cleanup() for interface in self.interfaces],
            return_exceptions=True
        )

        # Cancel producer tasks
        for task in self._producer_tasks:
            task.cancel()
        try:
            await asyncio.gather(*self._producer_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        # Clean up interfaces

        # Clear dictionary and queue
        async with self._lock:
            self._data_dict.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break
        # Shut down executor
        self._executor.shutdown(wait=True)
        logging.info("MultiInputInterface cleaned up")
