import asyncio
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Dict, Optional, Tuple

from contanos.metrics.prometheus import (
    MetricsLabelContext,
    service_backpressure_events_total,
    service_frames_dropped_total,
    service_interfaces_under_pressure,
    service_pending_frames,
)


class MultiInputInterface:
    """Improved wrapper for multiple input interfaces with intelligent synchronization."""

    def __init__(
        self,
        interfaces: List[Any],
        frame_timeout_sec: float = 20,
        sync_mode: str = "adaptive",
        max_memory_mb: int = 512,
        enable_backpressure_monitoring: bool = True,
        metrics_service: Optional[str] = None,
        metrics_task_id: Optional[str] = None,
        metrics_topic: str = "multi_input",
    ):
        self.interfaces = interfaces
        self.is_running = False
        self._executor = ThreadPoolExecutor(max_workers=len(interfaces))
        self._producer_tasks = []
        
        # Core data structures
        self._data_dict = defaultdict(lambda: {})  # {frame_id: {interface_idx: data}}
        self._queue = asyncio.Queue(maxsize=10000)
        self._lock = asyncio.Lock()
        self._num_interfaces = len(interfaces)
        
        # Improved synchronization parameters
        self.frame_timeout_sec = frame_timeout_sec
        self.sync_mode = sync_mode  # "strict", "adaptive", "partial"
        self.max_memory_mb = max_memory_mb
        
        # Adaptive synchronization state
        self._frame_id_order = deque()  # Use deque for better performance
        self._last_emitted_frame_id = -1
        self._interface_speeds = [0.0] * len(interfaces)  # frames/sec for each interface
        self._interface_last_seen = [0] * len(interfaces)  # last frame_id from each interface
        # Remove unused variable to follow KISS principle
        # self._speed_update_window = deque(maxlen=100)  # sliding window for speed calculation
        
        # Dynamic buffer management
        self._base_max_pending = 5000  # Base buffer size
        self.max_pending_frames = self._base_max_pending
        self._adaptive_window_size = self.frame_timeout_sec * 25
        
        # Performance monitoring
        self._sync_stats = {
            'total_frames_processed': 0,
            'frames_dropped_timeout': 0,
            'frames_dropped_overflow': 0,
            'partial_sync_count': 0,
            'last_speed_update': time.time()
        }
        
        # Backpressure monitoring
        self.enable_backpressure_monitoring = enable_backpressure_monitoring
        self._backpressure_stats = {
            'interfaces_under_pressure': [],
            'last_pressure_check': time.time()
        }

        self._metrics_context = MetricsLabelContext(
            service=metrics_service or "unknown",
            worker_id="multi_input",
            topic=metrics_topic or "multi_input",
            initial_task_id=metrics_task_id,
        )

    def _extract_task_id(self, payload: Dict[int, Any]) -> Optional[str]:
        for value in payload.values():
            if isinstance(value, dict) and value.get('task_id') is not None:
                return value.get('task_id')
        return None

    def _record_pending_frames(self, task_id: Optional[str] = None) -> None:
        labels = self._metrics_context.labels_for(task_id)
        service_pending_frames.labels(**labels).set(len(self._frame_id_order))

    def _record_frame_drop(self, task_id: Optional[str] = None) -> None:
        labels = self._metrics_context.labels_for(task_id)
        service_frames_dropped_total.labels(**labels).inc()

    def _update_interfaces_under_pressure_metric(self) -> None:
        labels = self._metrics_context.labels_for(None)
        service_interfaces_under_pressure.labels(**labels).set(
            len(self._backpressure_stats['interfaces_under_pressure'])
        )

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
            self._record_pending_frames()
            self._update_interfaces_under_pressure_metric()
            return True

        except Exception as e:
            logging.error(f"Failed to initialize MultiInputInterface: {e}")
            return False

    async def _interface_producer(self, interface_idx, interface):
        """Enhanced background task with intelligent synchronization."""
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

                task_id = data.get('task_id') if isinstance(data, dict) else None
                self._metrics_context.labels_for(task_id)

                # Update interface speed tracking
                await self._update_interface_speed(interface_idx, frame_id)

                # Monitor backpressure if enabled
                if self.enable_backpressure_monitoring:
                    await self._monitor_interface_backpressure(interface_idx, interface)

                async with self._lock:
                    # Add new frame_id if not already present
                    if frame_id not in self._data_dict:
                        self._frame_id_order.append(frame_id)

                    self._data_dict[frame_id][interface_idx] = data

                    # Intelligent buffer management
                    await self._manage_buffer_adaptively(frame_id)

                    # Check for completed frames with intelligent sync strategy
                    completed_payload = await self._check_frame_completion(frame_id)

                self._record_pending_frames(task_id)

                if completed_payload is not None:
                    payload_task_id = self._extract_task_id(completed_payload)
                    self._metrics_context.labels_for(payload_task_id)
                    await self._queue.put(completed_payload)
                    self._sync_stats['total_frames_processed'] += 1
                    logging.debug(f"Synchronized frame {completed_payload.get('frame_id')} with sync mode: {self.sync_mode}")

            except Exception as e:
                logging.error(f"Interface {interface_idx} error: {e}")
                await asyncio.sleep(1)
    
    async def _update_interface_speed(self, interface_idx: int, frame_id: int):
        """Update interface processing speed statistics."""
        current_time = time.time()
        last_frame = self._interface_last_seen[interface_idx]
        
        if last_frame > 0:
            time_window = current_time - self._sync_stats.get(f'interface_{interface_idx}_last_time', current_time)
            if time_window > 0:
                frame_delta = frame_id - last_frame
                speed = frame_delta / time_window
                self._interface_speeds[interface_idx] = speed
                
        self._interface_last_seen[interface_idx] = frame_id
        self._sync_stats[f'interface_{interface_idx}_last_time'] = current_time
    
    async def _monitor_interface_backpressure(self, interface_idx: int, interface: Any):
        """Monitor individual interface for backpressure signs."""
        if hasattr(interface, 'get_queue_status'):
            try:
                status = interface.get_queue_status()
                task_id = status.get('task_id')
                self._metrics_context.labels_for(task_id)
                usage_percent = status.get('usage_percent', 0)

                # Consider interface under pressure if queue usage > 75%
                if usage_percent > 75:
                    if interface_idx not in self._backpressure_stats['interfaces_under_pressure']:
                        self._backpressure_stats['interfaces_under_pressure'].append(interface_idx)
                        logging.warning(f"[BACKPRESSURE_MONITOR] Interface {interface_idx} under pressure: {usage_percent:.1f}% queue usage")
                        service_backpressure_events_total.labels(**self._metrics_context.current_labels).inc()
                else:
                    if interface_idx in self._backpressure_stats['interfaces_under_pressure']:
                        self._backpressure_stats['interfaces_under_pressure'].remove(interface_idx)
                        logging.info(f"[BACKPRESSURE_MONITOR] Interface {interface_idx} pressure relieved: {usage_percent:.1f}% queue usage")

                self._update_interfaces_under_pressure_metric()

            except Exception as e:
                logging.debug(f"Could not monitor backpressure for interface {interface_idx}: {e}")
    
    async def _manage_buffer_adaptively(self, frame_id: int):
        """Intelligent buffer management with adaptive strategies."""
        current_pending = len(self._frame_id_order)
        
        # Dynamic buffer size adjustment based on interface speeds
        if self.sync_mode == "adaptive":
            min_speed = min(self._interface_speeds) if any(self._interface_speeds) else 1.0
            max_speed = max(self._interface_speeds) if any(self._interface_speeds) else 1.0
            speed_ratio = max_speed / min_speed if min_speed > 0 else 1.0
            
            # Adjust buffer size based on speed disparity
            self.max_pending_frames = min(
                int(self._base_max_pending * (1 + speed_ratio * 0.5)),
                self.max_memory_mb * 1024 * 1024 // 10000  # Rough memory estimate
            )
            
            # Adaptive window size
            self._adaptive_window_size = max(
                self.frame_timeout_sec * 25,
                int(speed_ratio * self.frame_timeout_sec * 25)
            )
        
        # Smart cleanup strategy
        if current_pending > self.max_pending_frames:
            await self._smart_buffer_cleanup()
        
        # Sliding window cleanup with intelligence
        await self._adaptive_window_cleanup(frame_id)
    
    async def _smart_buffer_cleanup(self):
        """Intelligent buffer cleanup prioritizing less important frames."""
        if not self._frame_id_order:
            return
            
        cleanup_count = max(1, len(self._frame_id_order) // 10)  # Remove 10% of old frames
        
        for _ in range(cleanup_count):
            if not self._frame_id_order:
                break
                
            old_frame_id = self._frame_id_order.popleft()
            if old_frame_id in self._data_dict:
                frame_payload = self._data_dict[old_frame_id]
                task_id = self._extract_task_id(frame_payload)

                missing_interfaces = [i for i in range(self._num_interfaces)
                                    if i not in frame_payload]
                available_interfaces = list(frame_payload.keys())

                del self._data_dict[old_frame_id]
                self._sync_stats['frames_dropped_overflow'] += 1
                self._record_frame_drop(task_id)
                self._record_pending_frames(task_id)

                logging.warning(
                    f"[SMART_CLEANUP] Dropped frame {old_frame_id}. "
                    f"Missing interfaces: {missing_interfaces}, Available: {available_interfaces}. "
                    f"Pending: {len(self._frame_id_order)}/{self.max_pending_frames}"
                )
    
    async def _adaptive_window_cleanup(self, current_frame_id: int):
        """Adaptive sliding window cleanup."""
        window_start = self._last_emitted_frame_id
        window_end = window_start + self._adaptive_window_size
        
        if current_frame_id > window_end:
            # More conservative cleanup - only remove truly stale frames
            stale_threshold = self._last_emitted_frame_id - self.frame_timeout_sec
            
            while self._frame_id_order and self._frame_id_order[0] < stale_threshold:
                old_id = self._frame_id_order.popleft()
                if old_id in self._data_dict:
                    frame_payload = self._data_dict[old_id]
                    task_id = self._extract_task_id(frame_payload)
                    del self._data_dict[old_id]
                    self._sync_stats['frames_dropped_timeout'] += 1
                    self._record_frame_drop(task_id)
                    self._record_pending_frames(task_id)
                    logging.debug(f"Dropped stale frame {old_id} (threshold: {stale_threshold})")
    
    async def _check_frame_completion(self, frame_id: int) -> Optional[Dict[str, Any]]:
        """Intelligent frame completion check with multiple sync strategies."""
        frame_data = self._data_dict.get(frame_id, {})
        available_interfaces = len(frame_data)
        
        if self.sync_mode == "strict":
            # Strict mode: require all interfaces
            if available_interfaces == self._num_interfaces:
                return self._complete_frame(frame_id)
                
        elif self.sync_mode == "adaptive":
            # Adaptive mode: intelligent decision based on timing and availability
            if available_interfaces == self._num_interfaces:
                return self._complete_frame(frame_id)
            elif available_interfaces >= self._num_interfaces * 0.7:  # 70% threshold
                # Check if we've waited long enough
                frame_age = len([fid for fid in self._frame_id_order if fid <= frame_id])
                if frame_age > self.frame_timeout_sec * 5:  # Timeout-based partial sync
                    logging.warning(f"[ADAPTIVE_SYNC] Partial sync for frame {frame_id}: {available_interfaces}/{self._num_interfaces} interfaces")
                    self._sync_stats['partial_sync_count'] += 1
                    return self._complete_frame(frame_id, partial=True)
                    
        elif self.sync_mode == "partial":
            # Partial mode: accept majority of interfaces, but at least 2 for multi-input
            min_required = max(2, (self._num_interfaces + 1) // 2) if self._num_interfaces > 1 else 1
            if available_interfaces >= min_required:
                return self._complete_frame(frame_id, partial=True)
        
        return None
    
    def _complete_frame(self, frame_id: int, partial: bool = False) -> Dict[str, Any]:
        """Complete a frame and prepare for output."""
        completed_payload = self._data_dict[frame_id].copy()
        del self._data_dict[frame_id]
        
        # Remove from order list
        try:
            self._frame_id_order.remove(frame_id)
        except ValueError:
            pass
            
        if frame_id > self._last_emitted_frame_id:
            self._last_emitted_frame_id = frame_id

        # Merge all interface data (保持原来的格式)
        merged_data = {}
        for idx in sorted(completed_payload.keys()):
            part = completed_payload[idx]
            if isinstance(part, dict):
                merged_data.update(part)  # simple merge, later keys overwrite earlier ones if conflict

        task_id = merged_data.get('task_id') or self._extract_task_id(completed_payload)
        self._record_pending_frames(task_id)

        # Data integrity check - ensure critical fields exist
        if partial and 'image_bytes' not in merged_data:
            logging.warning(f"[DATA_INTEGRITY] Frame {frame_id} missing image_bytes in partial sync - skipping")
            return None  # Don't output incomplete data
                
        # Add sync metadata as debug info only (不影响主要数据结构)
        if partial:
            logging.debug(f"[PARTIAL_SYNC] Frame {frame_id}: {len(completed_payload)}/{self._num_interfaces} interfaces")
                
        return merged_data

    async def read_data(self) -> Dict[str, Any]:
        """Read synchronized data with improved timeout and error handling."""
        if not self.is_running:
            raise Exception("MultiInputInterface not initialized or stopped")

        try:
            frame_data = await asyncio.wait_for(self._queue.get(), timeout=self.frame_timeout_sec)
            self._queue.task_done()
            return frame_data  # Already merged in _complete_frame
            
        except asyncio.TimeoutError:
            # Enhanced timeout information with synchronization state
            async with self._lock:
                pending_frames = len(self._frame_id_order)
                oldest_frame = self._frame_id_order[0] if self._frame_id_order else None
                
                # Interface status summary
                interface_status = {}
                for i in range(self._num_interfaces):
                    interface_status[f"interface_{i}"] = {
                        "last_frame": self._interface_last_seen[i],
                        "speed_fps": round(self._interface_speeds[i], 2)
                    }
                
            logging.warning(
                f"[SYNC_TIMEOUT] Timeout waiting for synchronized data. "
                f"Pending: {pending_frames}, Oldest: {oldest_frame}, Mode: {self.sync_mode}. "
                f"Interface status: {interface_status}"
            )
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise Exception(f"Failed to read synchronized data: {e}")

    async def cleanup(self):
        """Clean up all interfaces and resources with performance stats."""
        self.is_running = False
        
        # Log final performance statistics
        self._log_performance_summary()

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

        # Clear dictionary and queue
        async with self._lock:
            self._data_dict.clear()
            self._frame_id_order.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break

        # Shut down executor
        self._executor.shutdown(wait=True)
        self._record_pending_frames()
        self._backpressure_stats['interfaces_under_pressure'].clear()
        self._update_interfaces_under_pressure_metric()
        logging.info("MultiInputInterface cleaned up")
    
    def _log_performance_summary(self):
        """Log performance summary on cleanup."""
        total_processed = self._sync_stats['total_frames_processed']
        dropped_timeout = self._sync_stats['frames_dropped_timeout']
        dropped_overflow = self._sync_stats['frames_dropped_overflow'] 
        partial_syncs = self._sync_stats['partial_sync_count']
        
        if total_processed > 0:
            timeout_rate = (dropped_timeout / total_processed) * 100
            overflow_rate = (dropped_overflow / total_processed) * 100
            partial_rate = (partial_syncs / total_processed) * 100
            
            logging.info(
                f"[SYNC_PERFORMANCE] Total frames: {total_processed}, "
                f"Timeout drops: {dropped_timeout} ({timeout_rate:.1f}%), "
                f"Overflow drops: {dropped_overflow} ({overflow_rate:.1f}%), "
                f"Partial syncs: {partial_syncs} ({partial_rate:.1f}%), "
                f"Mode: {self.sync_mode}, Max buffer: {self.max_pending_frames}"
            )
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current synchronization status for monitoring."""
        status = {
            'sync_mode': self.sync_mode,
            'is_running': self.is_running,
            'pending_frames': len(self._frame_id_order),
            'max_pending_frames': self.max_pending_frames,
            'last_emitted_frame_id': self._last_emitted_frame_id,
            'interface_speeds': self._interface_speeds.copy(),
            'interface_last_seen': self._interface_last_seen.copy(),
            'sync_stats': self._sync_stats.copy(),
            'adaptive_window_size': self._adaptive_window_size
        }
        
        # Add backpressure information if monitoring is enabled
        if self.enable_backpressure_monitoring:
            status['backpressure_stats'] = self._backpressure_stats.copy()
            
            # Get detailed interface queue status
            interface_queue_status = []
            for idx, interface in enumerate(self.interfaces):
                if hasattr(interface, 'get_queue_status'):
                    try:
                        queue_status = interface.get_queue_status()
                        interface_queue_status.append({
                            'interface_idx': idx,
                            **queue_status
                        })
                    except Exception:
                        pass
            status['interface_queue_status'] = interface_queue_status
            
        return status
    
    def set_sync_mode(self, mode: str):
        """Dynamically change synchronization mode."""
        valid_modes = ["strict", "adaptive", "partial"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid sync mode: {mode}. Must be one of: {valid_modes}")
        self.sync_mode = mode
        logging.info(f"Synchronization mode changed to: {mode}")
