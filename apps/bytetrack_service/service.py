#!/usr/bin/env python3
"""
ByteTrack service using contanos framework for Kafka I/O and pose tracking.
Updated to use contanos framework with dynamic task_id support.
"""
import logging
import os
import sys
from typing import List

from contanos.ai_service import BaseAIService

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# Import ByteTrackWorker with error handling for different execution contexts
try:
    from .bytetrack_worker import ByteTrackWorker
except ImportError:
    # If relative import fails, try absolute import
    try:
        from bytetrack_worker import ByteTrackWorker
    except ImportError:
        from apps.bytetrack_service.bytetrack_worker import ByteTrackWorker

logger = logging.getLogger(__name__)


class ByteTrackService(BaseAIService):
    """ByteTrack tracking service using contanos framework with dynamic task support."""

    def get_service_name(self) -> str:
        return "ByteTrack Service"

    def get_service_config_key(self) -> str:
        return "bytetrack"

    def get_worker_class(self):
        return ByteTrackWorker

    def create_input_interfaces(self) -> List:
        """Create Kafka input interface for detection results."""
        from contanos.io.kafka_input_interface import KafkaInput
        
        input_config = self._get_kafka_input_config()
        logger.info(f"Input topic: {input_config.get('topic')}")
        logger.info(f"Consumer group: {input_config.get('group_id')}")

        return [KafkaInput(config=input_config)]

    def create_output_interface(self):
        """Create Kafka output interface for tracking results."""
        from contanos.io.kafka_output_interface import KafkaOutput
        
        output_config = self._get_kafka_output_config()
        logger.info(f"Output topic: {output_config.get('topic')}")

        return KafkaOutput(config=output_config)

    def get_model_config(self) -> dict:
        """Get ByteTrack model configuration."""
        bytetrack_config = self.config.get('bytetrack', {})
        
        return {
            'track_thresh': bytetrack_config.get('track_thresh', 0.45),
            'match_thresh': bytetrack_config.get('match_thresh', 0.8),
            'track_buffer': bytetrack_config.get('track_buffer', 25),
            'frame_rate': bytetrack_config.get('frame_rate', 25),
            'per_class': bytetrack_config.get('per_class', False)
        }

    def _parse_kafka_config_string(self, config_string: str) -> dict:
        """Parse Kafka configuration string format."""
        # Example: "kafka://localhost:9092,topic=yolox_detections_{task_id},group_id=bytetrack_consumers_{task_id}"
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

    def _get_kafka_input_config(self) -> dict:
        """Get Kafka input configuration from ByteTrack service config."""
        bytetrack_config = self.config.get('bytetrack', {})
        input_config_str = bytetrack_config.get('input', {}).get('config', '')

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
            'auto_offset_reset': consumer_settings.get('auto_offset_reset', 'earliest'),
            'max_poll_records': consumer_settings.get('max_poll_records', 1),
            'consumer_timeout_ms': consumer_settings.get('consumer_timeout_ms', 1000),
            'enable_auto_commit': consumer_settings.get('enable_auto_commit', True)
        }

        return config

    def _get_kafka_output_config(self) -> dict:
        """Get Kafka output configuration from ByteTrack service config."""
        bytetrack_config = self.config.get('bytetrack', {})
        output_config_str = bytetrack_config.get('output', {}).get('config', '')

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
    import argparse
    
    parser = argparse.ArgumentParser(
        description="ByteTrack Tracking Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-id camera1
  %(prog)s --task-id warehouse_cam --devices cpu
  %(prog)s --task-id production --config custom_config.yaml
  
Topic naming:
  Input topic:      yolox_detections_{task_id}
  Output topic:     bytetrack_tracking_{task_id}
  Consumer group:   bytetrack_consumers_{task_id}
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
    import asyncio
    
    args = parse_args()

    try:
        service = ByteTrackService(config_path=args.config, task_id=args.task_id)

        # Override config with command line arguments if provided
        if args.devices:
            device_list = args.devices.split(',')
            service.config.setdefault('bytetrack', {})['devices'] = device_list
            logger.info(f"Overriding devices with: {device_list}")

        await service.start_service()

    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
