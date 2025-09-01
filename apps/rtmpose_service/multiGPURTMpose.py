import os
from typing import List, Tuple

import numpy as np
import onnxruntime as ort
from rtmlib.tools.base import BaseTool  #
from rtmlib.tools.file import download_checkpoint
from rtmlib.tools.pose_estimation.post_processings import convert_coco_to_openpose, get_simcc_maximum
from rtmlib.tools.pose_estimation.pre_processings import bbox_xyxy2cs, top_down_affine


class MultiGPURTMPose(BaseTool):
    def __init__(self,
                 onnx_model: str,
                 model_input_size: tuple = (288, 384),
                 mean: tuple = (123.675, 116.28, 103.53),
                 std: tuple = (58.395, 57.12, 57.375),
                 to_openpose: bool = False,
                 backend: str = 'onnxruntime',
                 device: str = 'cpu'):
        if not os.path.exists(onnx_model):
            onnx_model = download_checkpoint(onnx_model)
        if backend == 'onnxruntime':
            if device.startswith("cuda"):
                gpu_id = int(device.split(":")[1]) if ":" in device else 0
                providers = [("CUDAExecutionProvider", {"device_id": gpu_id})]
            elif device == "cpu":
                providers = ["CPUExecutionProvider"]
            else:
                raise ValueError(f"Unsupported device: {device}")

            self.session = ort.InferenceSession(onnx_model, providers=providers)
            print(f"load {onnx_model} with {backend} backend on {device}")

        else:
            super().__init__(onnx_model, model_input_size, mean, std, backend, device)

        self.model_input_size = model_input_size
        self.mean = mean
        self.std = std
        self.backend = backend
        self.device = device
        self.to_openpose = to_openpose

    def __call__(self, image, bboxes=[]):
        if len(bboxes) == 0:
            bboxes = [[0, 0, image.shape[1], image.shape[0]]]

        keypoints, scores = [], []
        for bbox in bboxes:
            img, center, scale = self.preprocess(image, bbox)
            outputs = self.inference(img)
            kpts, score = self.postprocess(outputs, center, scale)

            keypoints.append(kpts)
            scores.append(score)

        keypoints = np.concatenate(keypoints, axis=0)
        scores = np.concatenate(scores, axis=0)

        if self.to_openpose:
            keypoints, scores = convert_coco_to_openpose(keypoints, scores)

        return keypoints, scores

    def preprocess(self, img: np.ndarray, bbox: list):
        """Do preprocessing for RTMPose model inference.

        Args:
            img (np.ndarray): Input image in shape.
            bbox (list):  xyxy-format bounding box of target.

        Returns:
            tuple:
            - resized_img (np.ndarray): Preprocessed image.
            - center (np.ndarray): Center of image.
            - scale (np.ndarray): Scale of image.
        """
        bbox = np.array(bbox)

        # get center and scale
        center, scale = bbox_xyxy2cs(bbox, padding=1.25)

        # do affine transformation
        resized_img, scale = top_down_affine(self.model_input_size, scale,
                                             center, img)
        # normalize image
        if self.mean is not None:
            self.mean = np.array(self.mean)
            self.std = np.array(self.std)
            resized_img = (resized_img - self.mean) / self.std

        return resized_img, center, scale

    def postprocess(
            self,
            outputs: List[np.ndarray],
            center: Tuple[int, int],
            scale: Tuple[int, int],
            simcc_split_ratio: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
        """Postprocess for RTMPose model output.

        Args:
            outputs (np.ndarray): Output of RTMPose model.
            model_input_size (tuple): RTMPose model Input image size.
            center (tuple): Center of bbox in shape (x, y).
            scale (tuple): Scale of bbox in shape (w, h).
            simcc_split_ratio (float): Split ratio of simcc.

        Returns:
            tuple:
            - keypoints (np.ndarray): Rescaled keypoints.
            - scores (np.ndarray): Model predict scores.
        """
        # decode simcc
        simcc_x, simcc_y = outputs
        locs, scores = get_simcc_maximum(simcc_x, simcc_y)
        keypoints = locs / simcc_split_ratio
        center = np.array(center)
        scale = np.array(scale, dtype=np.float32)
        # rescale keypoints
        keypoints = keypoints / self.model_input_size * scale
        keypoints = keypoints + center - scale / 2

        return keypoints, scores
