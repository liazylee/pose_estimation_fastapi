"""
Serialization utilities for frame encoding/decoding.
"""
import base64
import cv2
import numpy as np
from typing import Union, Tuple
import logging

logger = logging.getLogger(__name__)


def encode_frame_to_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    """
    Encode a numpy array frame to JPEG bytes.
    
    Args:
        frame: RGB numpy array
        quality: JPEG compression quality (0-100)
        
    Returns:
        JPEG encoded bytes
    """
    # Convert RGB to BGR for cv2
    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buffer = cv2.imencode('.jpg', bgr_frame, encode_params)
    
    if not success:
        raise ValueError("Failed to encode frame to JPEG")
    
    return buffer.tobytes()


def decode_jpeg_to_frame(jpeg_bytes: bytes) -> np.ndarray:
    """
    Decode JPEG bytes to numpy array.
    
    Args:
        jpeg_bytes: JPEG encoded bytes
        
    Returns:
        RGB numpy array
    """
    nparr = np.frombuffer(jpeg_bytes, np.uint8)
    bgr_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if bgr_frame is None:
        raise ValueError("Failed to decode JPEG bytes")
    
    # Convert BGR to RGB
    rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
    return rgb_frame


def encode_frame_to_base64(frame: np.ndarray, quality: int = 85) -> str:
    """
    Encode frame to base64 string.
    
    Args:
        frame: RGB numpy array
        quality: JPEG compression quality
        
    Returns:
        Base64 encoded string
    """
    jpeg_bytes = encode_frame_to_jpeg(frame, quality)
    return base64.b64encode(jpeg_bytes).decode('utf-8')


def decode_base64_to_frame(base64_str: str) -> np.ndarray:
    """
    Decode base64 string to numpy array.
    
    Args:
        base64_str: Base64 encoded string
        
    Returns:
        RGB numpy array
    """
    jpeg_bytes = base64.b64decode(base64_str)
    return decode_jpeg_to_frame(jpeg_bytes)


def serialize_image_for_kafka(image: np.ndarray, 
                            use_base64: bool = True,
                            quality: int = 85) -> Union[str, list]:
    """
    Serialize numpy image for Kafka transmission.
    
    Args:
        image: RGB numpy array
        use_base64: If True, return base64 string. If False, return bytes as list
        quality: JPEG compression quality
        
    Returns:
        Serialized image data
    """
    if use_base64:
        return encode_frame_to_base64(image, quality)
    else:
        jpeg_bytes = encode_frame_to_jpeg(image, quality)
        return list(jpeg_bytes)  # Convert to list for JSON serialization


def deserialize_image_from_kafka(image_data: Union[str, list],
                               is_base64: bool = True) -> np.ndarray:
    """
    Deserialize image data from Kafka message.
    
    Args:
        image_data: Serialized image data (base64 string or byte list)
        is_base64: Whether the data is base64 encoded
        
    Returns:
        RGB numpy array
    """
    if is_base64:
        return decode_base64_to_frame(image_data)
    else:
        jpeg_bytes = bytes(image_data)
        return decode_jpeg_to_frame(jpeg_bytes)


def resize_frame_if_needed(frame: np.ndarray, 
                         max_dimension: int = 1920) -> Tuple[np.ndarray, float]:
    """
    Resize frame if it exceeds maximum dimension while maintaining aspect ratio.
    
    Args:
        frame: Input frame
        max_dimension: Maximum width or height
        
    Returns:
        Tuple of (resized_frame, scale_factor)
    """
    height, width = frame.shape[:2]
    
    if width <= max_dimension and height <= max_dimension:
        return frame, 1.0
    
    if width > height:
        scale = max_dimension / width
    else:
        scale = max_dimension / height
    
    new_width = int(width * scale)
    new_height = int(height * scale)
    
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    logger.debug(f"Resized frame from {width}x{height} to {new_width}x{new_height}")
    
    return resized, scale