#!/usr/bin/env python3
"""
Jersey Number OCR Module
Integrates the jersey number recognition model for pose estimation pipeline.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Tuple, Optional, Dict

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

# Try to import the jersey nets model
try:
    from jersey_nets import JerseyNetMobileNet
except ImportError:
    logging.warning("jersey_nets not available, using mock implementation")
    JerseyNetMobileNet = None


class JerseyOCRModel:
    """Jersey number OCR model wrapper."""

    def __init__(self, device: str = "cuda", weights_path: str = None):
        self.device = device
        self.model = None
        self.transform = None
        self._initialize_model(weights_path)

    def _initialize_model(self, weights_path: str = None):
        """Initialize the jersey OCR model."""
        try:
            if JerseyNetMobileNet is None:
                logging.warning("Using mock OCR model - jersey_nets not available")
                return

            # Initialize model
            self.model = JerseyNetMobileNet(pretrained=True)

            # Load weights if provided
            if weights_path and Path(weights_path).exists():
                ckpt = torch.load(weights_path, map_location=self.device)
                state = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt

                self.model.load_state_dict(state, strict=False)
                logging.info(f"Loaded jersey OCR weights from {weights_path}")
            else:
                logging.warning(f"Jersey OCR weights not found at {weights_path}, using default weights")

            self.model.eval().to(self.device)

            # Initialize transforms
            self.transform = transforms.Compose([
                transforms.Resize((256, 192)),  # H, W (256x192)
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])

            logging.info(f"Jersey OCR model initialized on {self.device}")

        except Exception as e:
            logging.error(f"Failed to initialize jersey OCR model: {e}")
            self.model = None

    def _assemble_number(self, len_id: int, d1: int, d2: int) -> Tuple[str, int]:
        """Assemble number from predictions."""
        if len_id == 0:
            return "", -1
        if len_id == 1:
            return f"{d1}", d1
        return f"{d1}{d2}", d1 * 10 + d2

    def _mock_prediction(self) -> Dict:
        """Mock prediction for testing when model is not available."""
        # Return random jersey number for testing
        import random
        numbers = ["", "7", "10", "23", "45"]
        number_str = random.choice(numbers)
        number_int = int(number_str) if number_str else -1
        score = random.uniform(0.3, 0.9) if number_str else 0.1

        return {
            "number_str": number_str,
            "number_int": number_int,
            "score": score,
            "len_conf": score,
            "d1_conf": score,
            "d2_conf": score
        }

    def predict(self, image: np.ndarray, thr_len: float = 0.6, thr_digit: float = 0.5) -> Dict:
        """
        Predict jersey number from image.
        
        Args:
            image: Input image as numpy array (BGR format)
            thr_len: Threshold for length prediction
            thr_digit: Threshold for digit prediction
            
        Returns:
            Dictionary with prediction results
        """
        if self.model is None:
            return self._mock_prediction()

        try:
            # Convert BGR to RGB
            if len(image.shape) == 3:
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                image_rgb = image

            # Convert to PIL Image and apply transforms
            pil_image = Image.fromarray(image_rgb)
            input_tensor = self.transform(pil_image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                len_logits, d1_logits, d2_logits = self.model(input_tensor)

                len_prob = torch.softmax(len_logits, 1).cpu().numpy()[0]
                d1_prob = torch.softmax(d1_logits, 1).cpu().numpy()[0]
                d2_prob = torch.softmax(d2_logits, 1).cpu().numpy()[0]

                len_id = len_prob.argmax()
                d1 = d1_prob.argmax()
                d2 = d2_prob.argmax()

                pl, pd1, pd2 = float(len_prob[len_id]), float(d1_prob[d1]), float(d2_prob[d2])

                # Apply thresholds
                if len_id == 0 and pl < max(thr_len, 0.0):
                    pass  # Keep as no-number
                elif (len_id == 1 and (pl < thr_len or pd1 < thr_digit)) or \
                        (len_id == 2 and (pl < thr_len or pd1 < thr_digit or pd2 < thr_digit)):
                    # Downgrade to no-number
                    len_id, d1, d2 = 0, 0, 0
                    pl = max(pl, 1e-9)

                number_str, number_int = self._assemble_number(len_id, d1, d2)

                # Calculate overall score (geometric mean)
                if len_id == 0:
                    score = pl
                elif len_id == 1:
                    score = (pl * pd1) ** 0.5
                else:
                    score = (pl * pd1 * pd2) ** (1 / 3)

                return {
                    "number_str": number_str,
                    "number_int": number_int,
                    "score": float(score),
                    "len_conf": float(pl),
                    "d1_conf": float(pd1),
                    "d2_conf": float(pd2)
                }

        except Exception as e:
            logging.error(f"Jersey OCR prediction error: {e}")
            return {
                "number_str": "",
                "number_int": -1,
                "score": 0.0,
                "len_conf": 0.0,
                "d1_conf": 0.0,
                "d2_conf": 0.0
            }


class AsyncJerseyOCR:
    """Async wrapper for jersey OCR processing."""

    def __init__(self, device: str = "cuda", weights_path: str = None, max_workers: int = 2):
        self.ocr_model = JerseyOCRModel(device, weights_path)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    def shutdown(self):
        """Shutdown the async OCR."""
        self._shutdown = True
        self.executor.shutdown(wait=True)

    async def predict_async(self, image: np.ndarray, thr_len: float = 0.6, thr_digit: float = 0.5) -> Dict:
        """
        Async prediction wrapper.
        
        Args:
            image: Input image
            thr_len: Threshold for length prediction
            thr_digit: Threshold for digit prediction
            
        Returns:
            Prediction results
        """
        if self._shutdown:
            raise RuntimeError("AsyncJerseyOCR has been shutdown")

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor,
                self.ocr_model.predict,
                image,
                thr_len,
                thr_digit
            )
            return result
        except Exception as e:
            logging.error(f"Async jersey OCR error: {e}")
            return {
                "number_str": "",
                "number_int": -1,
                "score": 0.0,
                "len_conf": 0.0,
                "d1_conf": 0.0,
                "d2_conf": 0.0
            }


def extract_jersey_roi(image: np.ndarray, bbox: list, expand_ratio: float = 0.3) -> Optional[np.ndarray]:
    """
    Extract jersey ROI from person bounding box.
    
    Args:
        image: Full frame image
        bbox: Person bounding box [x1, y1, x2, y2]
        expand_ratio: Ratio to expand the ROI
        
    Returns:
        Cropped jersey ROI or None if invalid
    """
    try:
        h, w = image.shape[:2]
        x1, y1, x2, y2 = [int(coord) for coord in bbox]

        # Calculate jersey area (upper torso region)
        box_h = y2 - y1
        box_w = x2 - x1

        # Focus on upper chest area for jersey numbers
        jersey_y1 = y1 + int(box_h * 0.2)  # Skip head area
        jersey_y2 = y1 + int(box_h * 0.6)  # Upper torso
        jersey_x1 = x1 + int(box_w * 0.1)  # Slight margin
        jersey_x2 = x2 - int(box_w * 0.1)

        # Expand ROI
        expand_h = int((jersey_y2 - jersey_y1) * expand_ratio)
        expand_w = int((jersey_x2 - jersey_x1) * expand_ratio)

        jersey_y1 = max(0, jersey_y1 - expand_h)
        jersey_y2 = min(h, jersey_y2 + expand_h)
        jersey_x1 = max(0, jersey_x1 - expand_w)
        jersey_x2 = min(w, jersey_x2 + expand_w)

        # Ensure valid ROI
        if jersey_y2 <= jersey_y1 or jersey_x2 <= jersey_x1:
            return None

        roi = image[jersey_y1:jersey_y2, jersey_x1:jersey_x2]

        # Quality check
        if roi.size == 0 or min(roi.shape[:2]) < 20:
            return None

        return roi

    except Exception as e:
        logging.error(f"Error extracting jersey ROI: {e}")
        return None


def check_roi_quality(roi: np.ndarray, min_area: int = 400, min_sharpness: float = 100.0) -> bool:
    """
    Check ROI quality for OCR processing.
    
    Args:
        roi: Region of interest image
        min_area: Minimum area threshold
        min_sharpness: Minimum sharpness threshold (Laplacian variance)
        
    Returns:
        True if ROI meets quality requirements
    """
    try:
        if roi is None or roi.size == 0:
            return False

        # Check area
        area = roi.shape[0] * roi.shape[1]
        if area < min_area:
            return False

        # Check sharpness (Laplacian variance)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()

        return sharpness >= min_sharpness

    except Exception as e:
        logging.error(f"Error checking ROI quality: {e}")
        return False
