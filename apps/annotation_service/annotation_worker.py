"""
annotation worker.py
"""
import logging
from typing import Dict, List

import numpy as np

from contanos import BaseWorker
from contanos.visualizer.box_drawer import draw_boxes_on_frame


class AnnotationWorker(BaseWorker):
    """Annotation worker with contanos framework integration."""

    def __init__(self, worker_id: int, device: str,
                 model_config: Dict,
                 input_interface,
                 output_interface):
        super().__init__(worker_id, device, model_config,
                         input_interface, output_interface)

        logging.info(f"AnnotationWorker {worker_id} initialized on device {device}")

    def _model_init(self):
        """Initialize the annotation model."""
        self.box_drawer = draw_boxes_on_frame

    def _predict(self, inputs: Dict, metadata: Dict = None) -> Dict:
        """
        Annotate the input frame with bounding boxes.

        Args:
            input (Dict): Input data containing 'frame' and 'detections'.

        Returns:
            Dict: Annotated frame with bounding boxes drawn.
        """
        try:
            frame: np.ndarray = inputs.get('frame')
            detections: List = inputs.get('detections', [])

            if frame is None or not isinstance(frame, np.ndarray):
                logging.error(f"Worker {self.worker_id}: Invalid frame input")
                return {}

            annotated_frame = self.box_drawer(frame, detections)
            return {'annotated_frame': annotated_frame}

        except Exception as e:
            logging.error(f"AnnotationWorker {self.worker_id} prediction error: {e}")
            return {}
