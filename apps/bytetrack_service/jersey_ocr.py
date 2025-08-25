#!/usr/bin/env python3
"""
Jersey Number OCR Module
Integrates the jersey number recognition model for pose estimation pipeline.
"""

import logging
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from jersey_nets import JerseyNetMobileNet, JerseyNetConvNeXt


def assemble_number(len_id: int, d1: int, d2: int) -> Tuple[str, int]:
    if len_id == 0:
        return "", -1
    if len_id == 1:
        return f"{d1}", d1
    return f"{d1}{d2}", d1 * 10 + d2


class JerseyOCRModel:
    """OCR wrapper supporting multiple backbones"""

    def __init__(self,
                 backbone: str = "mobilenet_v3",
                 device: str = "cuda",
                 weights_path: str = None):
        self.device = device
        self.model = None
        self.transform = transforms.Compose([
            transforms.Resize((256, 192)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])
        self._initialize_model(backbone, weights_path)

    def _initialize_model(self, backbone: str, weights_path: str):
        try:
            if backbone == "mobilenet_v3":
                self.model = JerseyNetMobileNet(pretrained=False)
            else:
                self.model = JerseyNetConvNeXt(backbone_name=backbone,
                                               pretrained=False)

            if weights_path and Path(weights_path).exists():
                ckpt = torch.load(weights_path, map_location=self.device)
                state = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
                self.model.load_state_dict(state, strict=False)
                logging.info(f"Loaded OCR weights from {weights_path}")
            else:
                logging.warning(f"No OCR weights at {weights_path}, using random init")

            self.model.eval().to(self.device)
            logging.info(f"OCR model ({backbone}) initialized on {self.device}")

        except Exception as e:
            logging.error(f"Failed to init OCR model: {e}")
            self.model = None

    def predict(self, image: np.ndarray,
                thr_len: float = 0.6,
                thr_digit: float = 0.5) -> Dict:
        """Predict jersey number from image"""
        if self.model is None:
            return {"number_str": "", "number_int": -1, "score": 0.0,
                    "len_conf": 0.0, "d1_conf": 0.0, "d2_conf": 0.0}
        try:
            # preprocess
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(image_rgb)
            x = self.transform(pil_img).unsqueeze(0).to(self.device)

            with torch.no_grad():
                len_logits, d1_logits, d2_logits = self.model(x)

                len_prob = torch.softmax(len_logits, 1).cpu().numpy()[0]
                d1_prob = torch.softmax(d1_logits, 1).cpu().numpy()[0]
                d2_prob = torch.softmax(d2_logits, 1).cpu().numpy()[0]

                len_id = int(len_prob.argmax())
                d1 = int(d1_prob.argmax())
                d2 = int(d2_prob.argmax())

                pl, pd1, pd2 = float(len_prob[len_id]), float(d1_prob[d1]), float(d2_prob[d2])

                # threshold downgrade
                if (len_id == 1 and (pl < thr_len or pd1 < thr_digit)) or \
                        (len_id == 2 and (pl < thr_len or pd1 < thr_digit or pd2 < thr_digit)):
                    len_id, d1, d2 = 0, 0, 0
                    pl = max(pl, 1e-9)

                num_str, num_int = assemble_number(len_id, d1, d2)

                # score (geo mean)
                if len_id == 0:
                    score = pl
                elif len_id == 1:
                    score = (pl * pd1) ** 0.5
                else:
                    score = (pl * pd1 * pd2) ** (1 / 3)

                return {
                    "number_str": num_str,
                    "number_int": num_int,
                    "score": float(score),
                    "len_conf": pl,
                    "d1_conf": pd1,
                    "d2_conf": pd2
                }
        except Exception as e:
            logging.error(f"OCR prediction error: {e}")
            return {"number_str": "", "number_int": -1, "score": 0.0,
                    "len_conf": 0.0, "d1_conf": 0.0, "d2_conf": 0.0}


def extract_jersey_roi(image: np.ndarray, bbox: list, expand_ratio: float = 0.3):
    try:
        h, w = image.shape[:2]
        x1, y1, x2, y2 = [int(c) for c in bbox]
        box_h, box_w = y2 - y1, x2 - x1
        jy1, jy2 = y1 + int(box_h * 0.2), y1 + int(box_h * 0.6)
        jx1, jx2 = x1 + int(box_w * 0.1), x2 - int(box_w * 0.1)

        eh, ew = int((jy2 - jy1) * expand_ratio), int((jx2 - jx1) * expand_ratio)
        jy1, jy2 = max(0, jy1 - eh), min(h, jy2 + eh)
        jx1, jx2 = max(0, jx1 - ew), min(w, jx2 + ew)
        if jy2 <= jy1 or jx2 <= jx1:
            return None
        roi = image[jy1:jy2, jx1:jx2]
        return roi if roi.size > 0 else None
    except Exception as e:
        logging.error(f"ROI error: {e}")
        return None


def check_roi_quality(roi: np.ndarray, min_area: int = 400, min_sharpness: float = 100.0) -> bool:
    try:
        if roi is None or roi.size == 0:
            return False
        area = roi.shape[0] * roi.shape[1]
        if area < min_area:
            return False
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        return sharpness >= min_sharpness
    except Exception as e:
        logging.error(f"ROI quality check error: {e}")
        return False
