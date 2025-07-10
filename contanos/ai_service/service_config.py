from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class ServiceConfig:
    """Configuration for an AI service."""
    
    # Required fields (no defaults)
    service_name: str
    service_description: str
    service_factory: Callable
    
    # Optional fields (with defaults)
    service_version: str = "1.0.0"
    default_host: str = "0.0.0.0"
    default_port: int = 8000
    topic_config: Optional[Dict[str, Any]] = None
    default_config_path: str = "dev_pose_estimation_config.yaml"
    
    def get_topics_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Generate topics configuration for a specific task_id."""
        if not self.topic_config:
            return None
            
        topics = {}
        for key, template in self.topic_config.items():
            if isinstance(template, str):
                topics[key] = template.format(task_id=task_id)
            elif isinstance(template, list):
                topics[key] = [t.format(task_id=task_id) for t in template]
            elif isinstance(template, dict):
                topics[key] = {k: v.format(task_id=task_id) for k, v in template.items()}
            else:
                topics[key] = template
        return topics 