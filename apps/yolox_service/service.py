#!/usr/bin/env python3
"""
Refactored YOLOX service using BaseAIService to eliminate code duplication.
Only contains YOLOX-specific configuration and logic.
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict, Any, List

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.ai_service import BaseAIService
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.kafka_output_interface import KafkaOutput

# Import YOLOXWorker with error handling for different execution contexts
try:
    from .yolox_worker import YOLOXWorker
except ImportError:
    try:
        from yolox_worker import YOLOXWorker
    except ImportError:
        from apps.yolox_service.yolox_worker import YOLOXWorker

logger = logging.getLogger(__name__)


class YOLOXService(BaseAIService):
    """YOLOX detection service using BaseAIService framework."""

    def get_service_name(self) -> str:
        return "YOLOX Service"

    def get_service_config_key(self) -> str:
        return "yolox"

    def get_worker_class(self):
        return YOLOXWorker

    def create_input_interfaces(self) -> List[KafkaInput]:
        """Create Kafka input interface for raw frames."""
        input_config = self._get_kafka_input_config()
        logger.info(f"Input topic: {input_config.get('topic')}")
        logger.info(f"Consumer group: {input_config.get('group_id')}")
        
        return [KafkaInput(config=input_config)]

    def create_output_interface(self) -> KafkaOutput:
        """Create Kafka output interface for detections."""
        output_config = self._get_kafka_output_config()
        logger.info(f"Output topic: {output_config.get('topic')}")
        
        return KafkaOutput(config=output_config)

    def get_model_config(self) -> Dict[str, Any]:
        """Get YOLOX model configuration."""
        yolox_config = self.config.get('yolox', {})
        global_config = self.config.get('global', {})

        return {
            'onnx_model': yolox_config.get('onnx_model'),
            'model_input_size': yolox_config.get('model_input_size', [640, 640]),
            'backend': yolox_config.get('backend') or global_config.get('backend', 'onnxruntime')
        }

    def _parse_kafka_config_string(self, config_string: str) -> Dict[str, Any]:
        """Parse Kafka configuration string format."""
        # Example: "kafka://localhost:9092,topic=raw_frames_{task_id},group_id=yolox_consumers_{task_id}"
        config = {}

        # Extract URL part
        if "://" in config_string:
            protocol, rest = config_string.split("://", 1)
            if protocol != "kafka":
                raise ValueError(f"Expected kafka:// protocol, got {protocol}://")
        else:
            rest = config_string

        # Split by comma and parse parameters
        parts = rest.split(",")
        bootstrap_servers = parts[0]  # First part is always the server
        config["bootstrap_servers"] = bootstrap_servers

        # Parse additional parameters
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                config[key.strip()] = value.strip()

        return config

    def _get_kafka_input_config(self) -> Dict[str, Any]:
        """Get Kafka input configuration from YOLOX service config."""
        yolox_config = self.config.get('yolox', {})
        input_config_str = yolox_config.get('input', {}).get('config', '')

        # Substitute task_id
        input_config_str = self._substitute_task_id(input_config_str)

        # Parse Kafka config string
        kafka_config = self._parse_kafka_config_string(input_config_str)

        # Add default consumer settings from global Kafka config
        global_kafka = self.config.get('kafka', {})
        consumer_settings = global_kafka.get('consumer', {})

        # Merge configurations
        config = {
            'bootstrap_servers': kafka_config.get('bootstrap_servers'),
            'topic': kafka_config.get('topic'),
            'group_id': kafka_config.get('group_id'),
            'auto_offset_reset': consumer_settings.get('auto_offset_reset', 'latest'),
            'max_poll_records': consumer_settings.get('max_poll_records', 1),
            'consumer_timeout_ms': consumer_settings.get('consumer_timeout_ms', 1000),
            'enable_auto_commit': consumer_settings.get('enable_auto_commit', True)
        }

        return config

    def _get_kafka_output_config(self) -> Dict[str, Any]:
        """Get Kafka output configuration from YOLOX service config."""
        yolox_config = self.config.get('yolox', {})
        output_config_str = yolox_config.get('output', {}).get('config', '')

        # Substitute task_id
        output_config_str = self._substitute_task_id(output_config_str)

        # Parse Kafka config string
        kafka_config = self._parse_kafka_config_string(output_config_str)

        # Add default producer settings from global Kafka config
        global_kafka = self.config.get('kafka', {})
        producer_settings = global_kafka.get('producer', {})

        # Merge configurations
        config = {
            'bootstrap_servers': kafka_config.get('bootstrap_servers'),
            'topic': kafka_config.get('topic'),
            'acks': kafka_config.get('acks', producer_settings.get('acks', 'all')),
            'retries': kafka_config.get('retries', producer_settings.get('retries', 3)),
            'batch_size': producer_settings.get('batch_size', 16384),
            'linger_ms': producer_settings.get('linger_ms', 10),
            'buffer_memory': producer_settings.get('buffer_memory', 33554432),
            'compression_type': kafka_config.get('compression_type', producer_settings.get('compression_type', 'gzip'))
        }

        return config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="YOLOX Detection Service (Refactored)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-id camera1
  %(prog)s --task-id warehouse_cam --devices cuda:0,cuda:1
  %(prog)s --task-id production --config custom_config.yaml
  
Topic naming:
  Input topic:      raw_frames_{task_id}
  Output topic:     yolox_detections_{task_id}
  Consumer group:   yolox_consumers_{task_id}
        """
    )
    parser.add_argument('--config', type=str, default='dev_pose_estimation_config.yaml',
                        help='Path to configuration file')
    parser.add_argument('--task-id', type=str, required=True,
                        help='Task ID for dynamic topic generation (REQUIRED)')
    parser.add_argument('--devices', type=str,
                        help='Comma-separated list of devices (overrides config)')
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    try:
        service = YOLOXService(config_path=args.config, task_id=args.task_id)

        # Override config with command line arguments if provided
        if args.devices:
            device_list = args.devices.split(',')
            service.config.setdefault('yolox', {})['devices'] = device_list
            logger.info(f"Overriding devices with: {device_list}")

        await service.start_service()

    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main()) 