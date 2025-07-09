import asyncio
import functools
import logging
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict


class BaseWorker:
    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        self.worker_id = worker_id
        self.input_interface = input_interface
        self.output_interface = output_interface
        self.model_config = model_config
        self.device = device
        self._model_init()
        self._executor = ThreadPoolExecutor(max_workers=1)

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
        # logging.info(f"Worker {self.worker_id} started on {self.device}")
        while True:
            try:
                # logging.debug(f"Worker {self.worker_id} waiting for input data...")
                inputs = await self.input_interface.read_data()

                results = await loop.run_in_executor(
                    self._executor,
                    functools.partial(self._predict, inputs)
                )

                if results is not None:
                    output = self._format_results(results)

                    await self.output_interface.write_data(output)
                    # self.results.append(results)  # Store for verification
                    # logging.debug(f"Worker {self.worker_id} on {self.device} processed input -> output")
            except asyncio.TimeoutError:
                logging.info(f"Worker {self.worker_id} on {self.device} timed out, stopping")
                raise
            except Exception as e:
                logging.error(f"Worker {self.worker_id} on {self.device} error: {e}")
                raise
        logging.info(f"Worker {self.worker_id} on {self.device} finished")
