from typing import Dict, Tuple, List

import cv2
import numpy as np


def draw_pose(
        frame: np.ndarray,
        pose_estimations: List[List[Tuple[float, float]]],  # 多个人
        joint_color: Tuple[int, int, int] = (255, 0, 0),
        joint_radius: int = 1,
        line_thickness: int = 1
) -> np.ndarray:
    """
    Draw skeletons for multiple persons on the frame based on pose estimations.

    Args:
        frame (np.ndarray): The image frame to draw on.
        pose_estimations (List[List[Tuple[float, float]]]): List of pose estimations for multiple people.
        joint_color (tuple): Color for the joints.
        joint_radius (int): Radius of the joints.
        line_thickness (int): Thickness of skeleton lines.

    Returns:
        np.ndarray: The frame with drawn skeletons.
    """
    if not isinstance(frame, np.ndarray):
        raise ValueError("Frame must be a numpy array")

    PART_CONNECTIONS: Dict[str, List[Tuple[int, int]]] = {
        'left_arm': [(5, 7), (7, 9)],
        'right_arm': [(6, 8), (8, 10)],
        'torso': [(5, 6), (11, 12), (5, 11), (6, 12)],
        'left_leg': [(11, 13), (13, 15)],
        'right_leg': [(12, 14), (14, 16)],
        'head': [(0, 1), (1, 2), (2, 3), (3, 4)]
    }

    PART_COLORS: Dict[str, Tuple[int, int, int]] = {
        'left_arm': (255, 0, 0),  # Blue
        'right_arm': (0, 0, 255),  # Red
        'torso': (0, 255, 0),  # Green
        'left_leg': (0, 255, 255),  # Yellow
        'right_leg': (255, 0, 255),  # Magenta
        'head': (255, 255, 255)  # White
    }

    for person_pose in pose_estimations:
        if not isinstance(person_pose, list) or len(person_pose) == 0:
            continue

        for part, connections in PART_CONNECTIONS.items():
            color = PART_COLORS.get(part, (0, 255, 0))
            for idx_start, idx_end in connections:
                if idx_start >= len(person_pose) or idx_end >= len(person_pose):
                    continue
                x1, y1 = person_pose[idx_start]
                x2, y2 = person_pose[idx_end]
                if x1 <= 0 or y1 <= 0 or x2 <= 0 or y2 <= 0:
                    continue
                pt1 = (int(x1), int(y1))
                pt2 = (int(x2), int(y2))
                cv2.line(frame, pt1, pt2, color, thickness=line_thickness, lineType=cv2.LINE_AA)

        # Draw joints
        for (x, y) in person_pose:
            if x <= 0 or y <= 0:
                continue
            center = (int(x), int(y))
            cv2.circle(frame, center, joint_radius, joint_color, thickness=-1, lineType=cv2.LINE_AA)

    return frame
