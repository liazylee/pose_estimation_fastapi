import asyncio
import functools
import logging
import time
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from contanos.metrics.prometheus import (
    MetricsLabelContext,
    service_frame_processing_seconds,
    service_frames_errors_total,
    service_frames_processed_total,
)


class BaseWorker:
    def __init__(
        self,
        worker_id: int,
        device: str,
        model_config: Dict,
        input_interface,
        output_interface,
    ):
        self.worker_id = worker_id
        self.input_interface = input_interface
        self.output_interface = output_interface
        self.model_config = model_config
        self.device = device
        self._model_init()
        self._executor = ThreadPoolExecutor(max_workers=1)

        service_name = "unknown"
        task_id = None
        if isinstance(model_config, dict):
            service_name = model_config.get("service_name", service_name)
            task_id = model_config.get("task_id")

        topic = getattr(output_interface, "topic", None)
        if topic is None:
            topic = getattr(input_interface, "topic", None)
        if topic is None and hasattr(input_interface, "interfaces"):
            topic = "multi_input"
        if topic is None:
            topic = "unknown"

        self._metrics_context = MetricsLabelContext(
            service=service_name,
            worker_id=str(worker_id),
            topic=topic,
            initial_task_id=task_id,
        )

    @abstractmethod
    def _model_init(self):
        pass

    @abstractmethod
    def _predict(self, inputs: Any) -> Any:
        pass

    def _format_results(self, results: Any) -> dict:
        """Format the results for output."""
        return results

    async def run(self):
        loop = asyncio.get_running_loop()

        """Run the worker, reading from input and writing to output."""
        while True:
            try:
                inputs = await self.input_interface.read_data()

                if inputs is None:
                    continue

                task_id = inputs.get("task_id") if isinstance(inputs, dict) else None
                labels = self._metrics_context.labels_for(task_id)

                start_time = time.perf_counter()
                try:
                    results = await loop.run_in_executor(
                        self._executor,
                        functools.partial(self._predict, inputs),
                    )
                except Exception:
                    duration = time.perf_counter() - start_time
                    service_frame_processing_seconds.labels(**labels).observe(duration)
                    service_frames_errors_total.labels(**labels).inc()
                    raise

                duration = time.perf_counter() - start_time
                service_frame_processing_seconds.labels(**labels).observe(duration)
                service_frames_processed_total.labels(**labels).inc()

                if results is not None:
                    output = self._format_results(results)
                    if isinstance(output, dict) and isinstance(inputs, dict):
                        output.setdefault("task_id", inputs.get("task_id"))

                    await self.output_interface.write_data(output)
            except asyncio.TimeoutError:
                logging.info(f"Worker {self.worker_id} on {self.device} timed out, stopping")
                raise
            except Exception as e:
                logging.error(f"Worker {self.worker_id} on {self.device} error: {e}")
                raise

    def get_metrics_labels(self, task_id: Any = None) -> Dict[str, str]:
        """Expose metric labels for the current worker."""

        return self._metrics_context.labels_for(task_id)
