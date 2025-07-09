from typing import List

import numpy as np

from contanos.visualizer.box_drawer import draw_boxes_on_frame


class Visualizer:
    """
    Visualizer class for Contanos.
    This class is responsible for visualizing the data in Contanos.
    """

    def __init__(self, frame: np.ndarray, detections: List, estimation: List):
        """
        Initialize the Visualizer with data.
        :param frame: The image frame to visualize.
        """
        self.frame = frame
        self.detections = detections
        self.estimation = estimation

    def visualize(self):
        """
        Visualize the data.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def _draw_box(self) -> None:
        """
        Draw bounding boxes on the frame.
        This method should be implemented by subclasses.
        """
        self.frame = draw_boxes_on_frame(self.frame, self.detections, draw_labels=True)
