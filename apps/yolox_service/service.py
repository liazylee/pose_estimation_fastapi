#!/usr/bin/env python3
"""
YOLOX service using contanos framework for Kafka I/O and model inference.
Updated to use dev_pose_estimation_config.yaml format with dynamic task_id support.
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict, Any

import yaml

from contanos import MultiInputInterface

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
import torch
from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.kafka_output_interface import KafkaOutput
from contanos.utils.setup_logging import setup_logging

# Import YOLOXWorker with error handling for different execution contexts
try:
    from .yolox_worker import YOLOXWorker
except ImportError:
    # If relative import fails, try absolute import
    try:
        from yolox_worker import YOLOXWorker
    except ImportError:
        from apps.yolox_service.yolox_worker import YOLOXWorker

logger = logging.getLogger(__name__)


class YOLOXService:
    """YOLOX detection service using contanos framework with dynamic task support."""

    def __init__(self, config_path: str = "dev_pose_estimation_config.yaml", task_id: str = None):
        if task_id is None:
            raise ValueError("task_id is required and cannot be None. Please specify a task_id.")

        self.task_id = task_id
        self.config = self._load_config(config_path)
        self.processor = None
        self.service = None
        self.input_interface = None
        self.output_interface = None
        self.multi_input_interface = None

        logger.info(f"YOLOX Service initialized with task_id: '{self.task_id}'")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        # Try multiple possible locations for the config file
        # Get the absolute path of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))

        possible_paths = [
            config_path,  # Absolute path or relative to current working directory
            os.path.join(script_dir, config_path),  # Relative to service directory
            os.path.join(script_dir, "..", config_path),  # Relative to apps directory
            os.path.join(script_dir, "..", "..", config_path),  # Relative to project root
            # Additional backup paths
            os.path.join(os.getcwd(), config_path),  # Current working directory
            os.path.join(os.getcwd(), "apps", config_path),  # If running from project root
            os.path.join(os.getcwd(), "..", config_path),  # If running from subdirectory
        ]

        config_file = None
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                config_file = abs_path
                break

        if not config_file:
            logger.error(f"Configuration file '{config_path}' not found!")
            logger.error("Tried the following paths:")
            for i, path in enumerate(possible_paths, 1):
                abs_path = os.path.abspath(path)
                exists = "✅" if os.path.exists(abs_path) else "❌"
                logger.error(f"  {i}. {abs_path} {exists}")
            raise FileNotFoundError(f"Configuration file not found. Tried {len(possible_paths)} paths.")

        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Successfully loaded configuration from: {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {config_file}: {e}")
            raise

    def _substitute_task_id(self, config_string: str) -> str:
        """Replace {task_id} placeholder in config strings."""
        return config_string.replace("{task_id}", self.task_id)

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

    def _get_devices(self) -> list:
        """Get list of devices from configuration."""
        rtmpose_config = self.config.get('rtmpose', {})
        global_config = self.config.get('global', {})

        device_config = rtmpose_config.get('devices') or global_config.get('devices', 'cpu')

        if isinstance(device_config, str):
            if device_config.lower() == 'cuda':
                try:
                    if torch.cuda.is_available():
                        return ['cuda']
                    else:
                        logger.warning("CUDA not available, falling back to CPU")
                        return ['cpu']
                except ImportError:
                    logger.warning("PyTorch not available, using CPU")
                    return ['cpu']
            else:
                return [device_config]
        elif isinstance(device_config, list):
            return device_config
        else:
            logger.warning(f"Invalid device configuration: {device_config}, using CPU")
            return ['cpu']

    def _get_model_config(self) -> Dict[str, Any]:
        """Get model configuration from YOLOX service config."""
        yolox_config = self.config.get('yolox', {})
        global_config = self.config.get('global', {})

        model_config = {
            'onnx_model': yolox_config.get('onnx_model'),  # 改成 onnx_model
            'model_input_size': yolox_config.get('model_input_size', [640, 640]),
            'backend': yolox_config.get('backend') or global_config.get('backend', 'onnxruntime')
        }

        return model_config

    def _get_processing_config(self) -> Dict[str, Any]:
        """Get processing configuration."""
        global_config = self.config.get('global', {})

        return {
            'workers_per_device': global_config.get('num_workers_per_device', 1),
            'health_check_interval': 5.0,
            'max_restart_attempts': 3,
            'restart_cooldown': 3
        }

    async def start_service(self):
        """Start the YOLOX service using contanos framework."""
        try:
            # Setup logging
            global_config = self.config.get('global', {})
            log_level = global_config.get('log_level', 'INFO')
            setup_logging(log_level)
            logger.info(f"Starting YOLOX service with contanos framework for task: {self.task_id}")

            # Get input/output configurations
            input_config = self._get_kafka_input_config()
            output_config = self._get_kafka_output_config()

            logger.info(f"Input topic: {input_config.get('topic')}")
            logger.info(f"Output topic: {output_config.get('topic')}")
            logger.info(f"Consumer group: {input_config.get('group_id')}")

            # Initialize interfaces
            self.input_interface = KafkaInput(config=input_config)
            self.output_interface = KafkaOutput(config=output_config)
            self.multi_input_interface = MultiInputInterface(interfaces=[
                self.input_interface
            ])
            await self.multi_input_interface.initialize()
            await self.output_interface.initialize()

            # Get devices and model configuration
            devices = self._get_devices()
            model_config = self._get_model_config()
            processing_config = self._get_processing_config()

            logger.info(f"Using devices: {devices}")
            logger.info(f"Model config: {model_config}")

            # Create processor with workers
            workers, self.processor = create_a_processor(
                worker_class=YOLOXWorker,
                model_config=model_config,
                devices=devices,
                input_interface=self.multi_input_interface,
                output_interface=self.output_interface,
                num_workers_per_device=processing_config['workers_per_device']
            )

            logger.info(f"Created {len(workers)} workers across {len(devices)} devices")

            # Create and start service with monitoring
            self.service = BaseService(
                processor=self.processor,
                health_check_interval=processing_config['health_check_interval'],
                max_restart_attempts=processing_config['max_restart_attempts'],
                restart_cooldown=processing_config['restart_cooldown']
            )

            # Start service
            async with self.service:
                async with self.processor:
                    logger.info(f"YOLOX service started successfully for task: {self.task_id}")
                    logger.info("Service is running. Press Ctrl+C to stop.")

                    # Keep running until interrupted
                    try:
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        logger.info("Received interrupt signal, shutting down...")

        except Exception as e:
            logger.error(f"Error starting YOLOX service: {e}")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Clean up resources."""
        try:
            if self.input_interface:
                await self.input_interface.cleanup()
            if self.output_interface:
                await self.output_interface.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status."""
        if not self.processor:
            return {'status': 'not_started', 'task_id': self.task_id}

        worker_status = self.processor.get_worker_status()
        return {
            'status': 'running' if self.processor.is_running else 'stopped',
            'task_id': self.task_id,
            'workers': worker_status,
            'service_monitoring': self.service is not None
        }


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="YOLOX Detection Service",
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
            # Override device configuration
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
