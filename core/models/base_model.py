"""
Base AI Model Interface for standardized model implementations.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import numpy as np


class AIModel(ABC):
    """Abstract base class for all AI models in the pipeline."""
    
    def __init__(self, config: Dict):
        """
        Initialize model with configuration.
        
        Args:
            config: Model configuration dictionary containing paths, thresholds, etc.
        """
        self.config = config
        self.model_name = self.__class__.__name__
        
    @abstractmethod
    def predict(self, input_data: Dict) -> Dict:
        """
        Run inference on one input frame.
        
        Args:
            input_data: Dictionary containing:
                - task_id: str
                - frame_id: int
                - timestamp: str
                - image: np.ndarray (RGB format)
                - additional_data: Dict (optional, model-specific)
                
        Returns:
            Dictionary containing:
                - task_id: str
                - frame_id: int
                - timestamp: str
                - model: str
                - result: List (model-specific output)
        """
        pass
    @abstractmethod
    def predict_batch(self, input_batch: List[Dict]) -> List[Dict]:
        """
        Optional batch processing for performance.
        Default implementation just loops through single predictions.
        
        Args:
            input_batch: List of input_data dictionaries
            
        Returns:
            List of prediction results
        example:
        return [self.predict(input_data) for input_data in input_batch]
        """
        pass 
        
    
    def validate_input(self, input_data: Dict) -> bool:
        """Validate input data structure."""
        required_fields = ['task_id', 'frame_id', 'timestamp', 'image']
        return all(field in input_data for field in required_fields)
    
    def format_output(self, input_data: Dict, result: List) -> Dict:
        """Standard output formatting."""
        return {
            "task_id": input_data["task_id"],
            "frame_id": input_data["frame_id"],
            "timestamp": input_data["timestamp"],
            "model": self.model_name.lower().replace('model', ''),
            "result": result
        }