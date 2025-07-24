import asyncio
import heapq
import logging
from typing import Any, List, Dict, Optional


class MultiOutputInterface:
    """Wrapper for multiple output interfaces with frame ordering capability."""

    def __init__(self, interfaces: List[Any], enable_frame_ordering: bool = True):
        self.interfaces = interfaces
        self.enable_frame_ordering = enable_frame_ordering
        self.is_running = False

        if self.enable_frame_ordering:
            self._raw_queue = asyncio.Queue(maxsize=1000)
            self._ordered_queue = asyncio.Queue(maxsize=1000)
            self._frame_buffer = []
            self._expected_frame_id: Optional[int] = None
            self._ordering_task = None
            self._writer_task = None

    async def initialize(self) -> bool:
        try:
            results = await asyncio.gather(
                *[interface.initialize() for interface in self.interfaces],
                return_exceptions=True
            )

            self.interfaces = [
                iface for iface, result in zip(self.interfaces, results)
                if not isinstance(result, Exception) and result
            ]

            if not self.interfaces:
                logging.error("All output interfaces failed to initialize")
                return False

            self.is_running = True

            if self.enable_frame_ordering:
                self._ordering_task = asyncio.create_task(self._frame_ordering_producer())
                self._writer_task = asyncio.create_task(self._frame_writer_consumer())
                logging.info("Frame ordering enabled for output interfaces")

            logging.info(f"Initialized with {len(self.interfaces)} interface(s)")
            return True

        except Exception as e:
            logging.error(f"Initialization failed: {e}")
            return False

    async def write_data(self, results: Dict[str, Any]) -> bool:
        if not self.is_running:
            raise RuntimeError("MultiOutputInterface not initialized")

        try:
            if self.enable_frame_ordering:
                await self._raw_queue.put(results)
                return True
            else:
                return await self._write_to_all_interfaces(results)
        except Exception as e:
            logging.error(f"write_data error: {e}")
            return False

    async def _frame_ordering_producer(self):
        while self.is_running:
            try:
                try:
                    frame = await asyncio.wait_for(self._raw_queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

                frame_id = frame.get("frame_id")
                if frame_id is None:
                    await self._ordered_queue.put(frame)
                    self._raw_queue.task_done()
                    continue

                if self._expected_frame_id is None:
                    self._expected_frame_id = 0

                if frame_id < self._expected_frame_id:
                    logging.warning(f"Dropping old frame {frame_id}, expecting {self._expected_frame_id}")
                    self._raw_queue.task_done()
                    continue

                heapq.heappush(self._frame_buffer, (frame_id, frame))
                await self._flush_ordered_frames()

                self._raw_queue.task_done()

            except Exception as e:
                logging.error(f"Ordering error: {e}")
                await asyncio.sleep(0.1)

    async def _flush_ordered_frames(self):
        while self._frame_buffer:
            next_id, next_frame = self._frame_buffer[0]
            if next_id == self._expected_frame_id:
                heapq.heappop(self._frame_buffer)
                await self._ordered_queue.put(next_frame)
                self._expected_frame_id += 1
            elif len(self._frame_buffer) > 50:
                logging.warning(f"Skipping to frame {next_id} due to full buffer")
                self._expected_frame_id = next_id
            else:
                break

    async def _frame_writer_consumer(self):
        while self.is_running:
            try:
                frame = await self._ordered_queue.get()
                await self._write_to_all_interfaces(frame)
                self._ordered_queue.task_done()
            except Exception as e:
                logging.error(f"Writer error: {e}")
                await asyncio.sleep(0.1)

    async def _write_to_all_interfaces(self, results: Dict[str, Any]) -> bool:
        try:
            tasks = [iface.write_data(results) for iface in self.interfaces]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            success_count = sum(1 for r in results if r is True)
            if success_count == 0:
                logging.error("All writes failed")
                return False
            elif success_count < len(tasks):
                logging.warning(f"Only {success_count}/{len(tasks)} writes succeeded")
            return True
        except Exception as e:
            logging.error(f"Write error: {e}")
            return False

    async def cleanup(self):
        self.is_running = False

        # Cancel tasks
        for task in [self._ordering_task, self._writer_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Cleanup interfaces
        tasks = []
        for iface in self.interfaces:
            try:
                tasks.append(iface.cleanup())
            except Exception as e:
                logging.error(f"Cleanup task error: {e}")
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logging.info("MultiOutputInterface cleaned up")

    def get_status(self) -> Dict[str, Any]:
        status = {
            'is_running': self.is_running,
            'interface_count': len(self.interfaces),
            'frame_ordering_enabled': self.enable_frame_ordering,
            'interfaces': []
        }

        if self.enable_frame_ordering:
            status['frame_ordering'] = {
                'expected_frame_id': self._expected_frame_id,
                'buffer_size': len(self._frame_buffer),
                'raw_queue_size': self._raw_queue.qsize(),
                'ordered_queue_size': self._ordered_queue.qsize(),
            }

        for idx, iface in enumerate(self.interfaces):
            info = {
                'index': idx,
                'type': type(iface).__name__,
                'is_running': getattr(iface, 'is_running', 'unknown')
            }
            for attr in ['output_path', 'addr', 'topic']:
                if hasattr(iface, attr):
                    info[attr] = getattr(iface, attr)
            status['interfaces'].append(info)

        return status
