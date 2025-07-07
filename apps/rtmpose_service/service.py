#!/usr/bin/env python3
"""
RTMPose service using contanos framework for Kafka I/O and pose estimation.
Updated to use contanos framework with dynamic task_id support.
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict, Any

import yaml

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.kafka_output_interface import KafkaOutput
from contanos.utils.setup_logging import setup_logging
from contanos.utils.yaml_config_loader import ConfigLoader

# Import RTMPoseWorker with error handling for different execution contexts
try:
    from .rtmpose_worker import RTMPoseWorker
except ImportError:
    # If relative import fails, try absolute import
    try:
        from rtmpose_worker import RTMPoseWorker
    except ImportError:
        from apps.rtmpose_service.rtmpose_worker import RTMPoseWorker

logger = logging.getLogger(__name__)


class RTMPoseService:
    """RTMPose pose estimation service using contanos framework with dynamic task support."""

    def __init__(self, task_id: str, config_path: str = "apps/dev_pose_estimation_config.yaml"):
        self.task_id = task_id
        self.config_path = config_path
        
        # Load configuration
        self.config_loader = ConfigLoader(config_path)
        self.config = self.config_loader.config
        
        # Initialize interfaces
        self.input_interface = None
        self.output_interface = None

    def _substitute_task_id(self, config_str: str) -> str:
        """Substitute {task_id} placeholder in configuration strings."""
        return config_str.replace('{task_id}', self.task_id)

    def _parse_kafka_config_string(self, config_str: str) -> Dict[str, Any]:
        """Parse Kafka configuration string into dict."""
        from contanos.utils.parse_config_string import parse_config_string
        return parse_config_string(config_str)

    def _get_devices(self) -> list:
        """Get devices from configuration."""
        rtmpose_config = self.config.get('rtmpose', {})
        devices_config = rtmpose_config.get('devices', 'cuda')
        
        if isinstance(devices_config, str):
            if devices_config == 'cuda':
                # Auto-detect CUDA devices
                import torch
                if torch.cuda.is_available():
                    return [f'cuda:{i}' for i in range(torch.cuda.device_count())]
                else:
                    return ['cpu']
            elif devices_config == 'cpu':
                return ['cpu']
            else:
                return [devices_config]
        elif isinstance(devices_config, list):
            return devices_config
        else:
            return ['cpu']

    def _get_model_config(self) -> Dict[str, Any]:
        """Get model configuration for RTMPose."""
        rtmpose_config = self.config.get('rtmpose', {})
        
        model_config = {
            'model_path': rtmpose_config.get('model_path'),
            'model_url': rtmpose_config.get('model_url'),
            'backend': rtmpose_config.get('backend', 'onnxruntime'),
            'device': 'cuda',  # Will be overridden per worker
        }
        
        # Add model-specific parameters
        if 'model' in rtmpose_config:
            model_config.update(rtmpose_config['model'])
            
        return model_config

    def _get_kafka_input_config(self) -> Dict[str, Any]:
        """Get Kafka input configuration from RTMPose service config."""
        rtmpose_config = self.config.get('rtmpose', {})
        input_config_str = rtmpose_config.get('input', {}).get('config', '')

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
        """Get Kafka output configuration from RTMPose service config."""
        rtmpose_config = self.config.get('rtmpose', {})
        output_config_str = rtmpose_config.get('output', {}).get('config', '')

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

    def _get_processing_config(self) -> Dict[str, Any]:
        """Get processing configuration."""
        global_config = self.config.get('global', {})

        return {
            'workers_per_device': global_config.get('num_workers_per_device', 1),
            'health_check_interval': 5.0,
            'max_restart_attempts': 3,
            'restart_cooldown': 30.0
        }

    async def start_service(self):
        """Start the RTMPose service using contanos framework."""
        try:
            # Setup logging
            global_config = self.config.get('global', {})
            log_level = global_config.get('log_level', 'INFO')
            setup_logging(log_level)
            logger.info(f"Starting RTMPose service with contanos framework for task: {self.task_id}")

            # Get input/output configurations
            input_config = self._get_kafka_input_config()
            output_config = self._get_kafka_output_config()

            logger.info(f"Input topic: {input_config.get('topic')}")
            logger.info(f"Output topic: {output_config.get('topic')}")
            logger.info(f"Consumer group: {input_config.get('group_id')}")

            # Initialize interfaces
            self.input_interface = KafkaInput(config=input_config)
            self.output_interface = KafkaOutput(config=output_config)

            await self.input_interface.initialize()
            await self.output_interface.initialize()

            # Get devices and model configuration
            devices = self._get_devices()
            model_config = self._get_model_config()
            processing_config = self._get_processing_config()

            logger.info(f"Using devices: {devices}")
            logger.info(f"Model config: {model_config}")

            # Create workers and processor
            workers, processor = create_a_processor(
                worker_class=RTMPoseWorker,
                model_config=model_config,
                devices=devices,
                input_interface=self.input_interface,
                output_interface=self.output_interface,
                num_workers_per_device=processing_config['workers_per_device']
            )

            # Start service with monitoring
            service = BaseService(
                processor=processor,
                health_check_interval=processing_config['health_check_interval'],
                max_restart_attempts=processing_config['max_restart_attempts'],
                restart_cooldown=processing_config['restart_cooldown']
            )

            # Run the service
            async with service:
                await processor.start()
                logger.info("RTMPose service started successfully")
                await processor.wait_for_completion()

        except Exception as e:
            logger.error(f"Failed to start RTMPose service: {e}")
            raise
        finally:
            # Cleanup
            if self.input_interface:
                await self.input_interface.cleanup()
            if self.output_interface:
                await self.output_interface.cleanup()


async def main():
    """Main entry point for RTMPose service."""
    parser = argparse.ArgumentParser(description='RTMPose Service with Contanos Framework')
    parser.add_argument('--task_id', type=str, required=True,
                        help='Task ID for processing pipeline')
    parser.add_argument('--config', type=str, 
                        default='apps/dev_pose_estimation_config.yaml',
                        help='Path to configuration file')
    
    args = parser.parse_args()
    
    # Create and start service
    service = RTMPoseService(task_id=args.task_id, config_path=args.config)
    await service.start_service()


if __name__ == "__main__":
    asyncio.run(main())