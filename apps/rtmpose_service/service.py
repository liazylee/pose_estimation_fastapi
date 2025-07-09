#!/usr/bin/env python3
"""
RTMPose service for pose estimation.
Consumes raw_frames and yolox_detections from Kafka, performs pose estimation, and outputs results to Kafka.
"""
import asyncio
import logging
import os
import sys
from typing import Dict, Any

import torch
import yaml

from contanos.io.multi_input_interface import MultiInputInterface

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.kafka_output_interface import KafkaOutput
from contanos.utils.setup_logging import setup_logging

# Import RTMPoseWorker with error handling for different execution contexts
try:
    from .rtmpose_worker import RTMPoseWorker
except ImportError:
    # If relative import fails, try absolute import
    try:
        from rtmpose_worker import RTMPoseWorker
    except ImportError:
        from apps.rtmpose_service.rtmpose_worker import RTMPoseWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RTMPoseService:
    """RTMPose estimation service using contanos framework with dynamic task support."""

    def __init__(self, config_path: str = "dev_pose_estimation_config.yaml", task_id: str = None):
        if task_id is None:
            raise ValueError("task_id is required and cannot be None. Please specify a task_id.")

        self.task_id = task_id
        self.config = self._load_config(config_path)
        self.processor = None
        self.service = None
        self.multi_input_interface = None
        self.output_interface = None

        logger.info(f"RTMPose Service initialized with task_id: '{self.task_id}'")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        # Try multiple possible locations for the config file
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
            logger.error(f"Configuration file not found: {config_path}")
            logger.error(f"Searched paths: {possible_paths}")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        logger.info(f"Loading configuration from: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        return config

    def _get_kafka_input_config(self, topic_suffix: str, group_suffix: str) -> Dict[str, Any]:
        """Get Kafka input configuration for a specific topic."""
        kafka_config = self.config.get('kafka', {})

        return {
            **kafka_config,
            'topic': f"{topic_suffix}_{self.task_id}",
            'group_id': f"{group_suffix}_{self.task_id}",
        }

    def _get_kafka_output_config(self) -> Dict[str, Any]:
        """Get Kafka output configuration."""
        kafka_config = self.config.get('kafka', {})

        return {
            **kafka_config,
            'topic': f"rtmpose_results_{self.task_id}",
        }

    def _get_devices(self) -> list:
        """Get list of devices from configuration."""
        rtmpose_config = self.config.get('rtmpose', {})
        global_config = self.config.get('global', {})

        device_config = rtmpose_config.get('devices') or global_config.get('devices', 'cpu')

        if isinstance(device_config, str):
            if device_config.lower() == 'cuda':
                # 对于多GPU支持，但保持简单的设备格式
                try:
                    if torch.cuda.is_available():
                        # 返回单个 'cuda' 而不是 'cuda:0', 'cuda:1' 列表
                        # 让 RTMPose 自己处理设备选择
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
        """Get model configuration from RTMPose service config."""
        rtmpose_config = self.config.get('rtmpose', {})
        global_config = self.config.get('global', {})

        model_config = {
            'onnx_model': rtmpose_config.get('onnx_model'),
            'model_input_size': rtmpose_config.get('model_input_size'),
            'backend': rtmpose_config.get('backend') or global_config.get('backend', 'onnxruntime')
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
        """Start the RTMPose service using contanos framework."""
        try:
            # Setup logging
            global_config = self.config.get('global', {})
            log_level = global_config.get('log_level', 'INFO')
            setup_logging(log_level)
            logger.info(f"Starting RTMPose service with contanos framework for task: {self.task_id}")

            # Get input/output configurations
            frames_config = self._get_kafka_input_config('raw_frames', 'rtmpose_raw')
            detections_config = self._get_kafka_input_config('yolox_detections', 'rtmpose_det')
            output_config = self._get_kafka_output_config()

            logger.info(f"Frames input topic: {frames_config.get('topic')}")
            logger.info(f"Detections input topic: {detections_config.get('topic')}")
            logger.info(f"Output topic: {output_config.get('topic')}")

            # Initialize input interfaces
            kafka_frame_input = KafkaInput(config=frames_config)
            kafka_detection_input = KafkaInput(config=detections_config)

            # Initialize MultiInputInterface for synchronized input
            self.multi_input_interface = MultiInputInterface(interfaces=[
                kafka_frame_input,
                kafka_detection_input
            ])
            await self.multi_input_interface.initialize()
            logger.info("Initialized MultiInputInterface for RTMPose service")

            # Initialize output interface
            self.output_interface = KafkaOutput(config=output_config)
            await self.output_interface.initialize()

            # Get devices and model configuration
            devices = self._get_devices()
            model_config = self._get_model_config()
            processing_config = self._get_processing_config()

            logger.info(f"Using devices: {devices}")
            logger.info(f"Model config: {model_config}")

            # Create processor with workers
            workers, self.processor = create_a_processor(
                worker_class=RTMPoseWorker,
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
                    logger.info(f"RTMPose service started successfully for task: {self.task_id}")
                    logger.info("Service is running. Press Ctrl+C to stop.")

                    # Keep running until interrupted
                    try:
                        while True:
                            await asyncio.sleep(1)
                    except KeyboardInterrupt:
                        logger.info("Received interrupt signal, shutting down...")

        except Exception as e:
            logger.error(f"Error starting RTMPose service: {e}")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Clean up resources."""
        try:
            if self.multi_input_interface:
                await self.multi_input_interface.cleanup()
            if self.output_interface:
                await self.output_interface.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='RTMPose Service')
    parser.add_argument('--task-id', required=True, help='Task ID')
    parser.add_argument('--config', default='dev_pose_estimation_config.yaml',
                        help='Configuration file path')

    args = parser.parse_args()

    # Create and start service
    service = RTMPoseService(args.config, args.task_id)

    try:
        asyncio.run(service.start_service())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
