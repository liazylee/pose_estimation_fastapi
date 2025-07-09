#!/usr/bin/env python3
"""
Annotation service for drawing detection overlays and generating RTSP output.
Consumes raw_frames and yolox_detections from Kafka, renders annotations, and outputs to RTSP.
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict, Any

import torch
import yaml

from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.multi_input_interface import MultiInputInterface
from contanos.io.multi_output_interface import MultiOutputInterface
from contanos.io.rtsp_output_interface import RTSPOutput
from contanos.io.video_output_interface import VideoOutput

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.utils.setup_logging import setup_logging

# Import AnnotationWorker with error handling for different execution contexts
try:
    from .annotation_worker import AnnotationWorker
except ImportError:
    # If relative import fails, try absolute import
    try:
        from annotation_worker import AnnotationWorker
    except ImportError:
        from apps.annotation_service.annotation_worker import AnnotationWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnnotationService:
    """Annotation service using contanos framework with dynamic task support."""

    def __init__(self, config_path: str = "dev_pose_estimation_config.yaml", task_id: str = None):
        if task_id is None:
            raise ValueError("task_id is required and cannot be None. Please specify a task_id.")

        self.task_id = task_id
        self.config = self._load_config(config_path)
        self.processor = None
        self.service = None

        # Processing state for stats
        self.frame_count = 0
        self.detection_count = 0
        self._stop_event = asyncio.Event()
        logger.info(f"Annotation Service initialized with task_id: '{self.task_id}'")

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

    def _get_rtsp_output_config(self) -> Dict[str, Any]:
        """Get RTSP output configuration."""
        annotation_config = self.config.get('annotation', {})
        rtsp_config = self.config.get('rtsp', {})

        # Parse output config if it exists
        output_config = annotation_config.get('output', {})
        if output_config.get('type') == 'rtsp':
            config_str = output_config.get('config', '')
            # Parse config string: "rtsp://localhost:8554,topic=outstream_{task_id},width=1920,height=1080,fps=25"
            parts = config_str.split(',')
            addr = parts[0] if parts else rtsp_config.get('output_stream', 'rtsp://localhost:8554')

            config = {
                'addr': addr,
                'topic': f"outstream_{self.task_id}",
                'width': rtsp_config.get('output_width', 1920),
                'height': rtsp_config.get('output_height', 1080),
                'fps': rtsp_config.get('output_fps', 25)
            }

            # Parse additional parameters from config string
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    if key == 'topic':
                        config['topic'] = value.format(task_id=self.task_id)
                    elif key in ['width', 'height', 'fps']:
                        config[key] = int(value)

            return config

        # Default configuration using rtsp config section
        return {
            'addr': rtsp_config.get('output_stream', 'rtsp://localhost:8554'),
            'topic': f"outstream_{self.task_id}",
            'width': rtsp_config.get('output_width', 1920),
            'height': rtsp_config.get('output_height', 1080),
            'fps': rtsp_config.get('output_fps', 25)
        }

    def _get_video_output_config(self) -> Dict[str, Any]:
        """Get video output configuration."""
        annotation_config = self.config.get('annotation', {})
        video_config = annotation_config.get('video_output', {})

        return {
            'task_id': self.task_id,
            'output_dir': video_config.get('output_dir', 'output_videos'),
            'enabled': video_config.get('enabled', True),
            'filename_template': video_config.get('filename_template', 'annotated_{task_id}_{timestamp}.mp4'),
            'width': video_config.get('width', 1920),
            'height': video_config.get('height', 1080),
            'fps': video_config.get('fps', 25),
            'codec': video_config.get('codec', 'libx264'),
            'preset': video_config.get('preset', 'fast'),
            'crf': video_config.get('crf', 23),
            'bitrate': video_config.get('bitrate', '2000k'),
            'pixel_format': video_config.get('pixel_format', 'yuv420p'),
            'queue_max_len': video_config.get('queue_max_len', 100)
        }

    def _get_devices(self) -> list:
        """Get list of devices from configuration."""
        annotation_config = self.config.get('annotation', {})
        global_config = self.config.get('global', {})

        device_config = annotation_config.get('devices') or global_config.get('devices', 'cpu')

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
        """Get model configuration for annotation service."""
        annotation_config = self.config.get('annotation', {})

        model_config = {
            'debug_output_dir': annotation_config.get('debug_output_dir', 'debug_frames'),
            'video_output': annotation_config.get('video_output', {}),
            'task_id': self.task_id
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
        """Start the Annotation service using contanos framework."""
        try:
            # Setup logging
            global_config = self.config.get('global', {})
            log_level = global_config.get('log_level', 'INFO')
            setup_logging(log_level)
            logger.info(f"Starting Annotation service with contanos framework for task: {self.task_id}")

            # Get input/output configurations
            frames_config = self._get_kafka_input_config('raw_frames', 'annotation_raw')
            detections_config = self._get_kafka_input_config('yolox_detections', 'annotation_track')
            poses_config = self._get_kafka_input_config('rtmpose_results', 'annotation_pose')

            # Get output configurations
            rtsp_config = self._get_rtsp_output_config()
            video_config = self._get_video_output_config()

            # Initialize input interfaces
            frames_input = KafkaInput(frames_config)
            detections_input = KafkaInput(detections_config)
            poses_input = KafkaInput(poses_config)
            multi_input = MultiInputInterface([frames_input, detections_input, poses_input])
            await multi_input.initialize()
            # Initialize output interfaces
            output_interfaces = []

            # Always add RTSP output
            rtsp_output = RTSPOutput(rtsp_config)
            output_interfaces.append(rtsp_output)

            # Add video output if enabled
            if video_config.get('enabled', True):  # Default to enabled
                video_output = VideoOutput(video_config)
                output_interfaces.append(video_output)
                logger.info(f"Video output enabled: {video_config.get('output_dir', 'output_videos')}")
            else:
                logger.info("Video output disabled")

            multi_output = MultiOutputInterface(output_interfaces)
            await multi_output.initialize()
            # Get devices and processing configuration  
            devices = self._get_devices()
            processing_config = self._get_processing_config()
            model_config = self._get_model_config()

            logger.info(f"Using devices: {devices}")
            logger.info(f"Workers per device: {processing_config['workers_per_device']}")

            # Create processor with workers using correct parameters
            workers, self.processor = create_a_processor(
                worker_class=AnnotationWorker,
                model_config=model_config,
                devices=devices,
                input_interface=multi_input,
                output_interface=multi_output,
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
                    logger.info(f"Annotation service started successfully for task: {self.task_id}")
                    logger.info("Service is running. Press Ctrl+C to stop.")
                    try:
                        while True:
                            if all(t.done() for t in self.processor.worker_tasks):
                                logger.info("All worker tasks completed. Exiting service.")
                                break
                            await asyncio.sleep(1)  # Keep the service running
                    except asyncio.CancelledError:
                        logger.info("Service stopped by user")
                    except KeyboardInterrupt:
                        logger.info("Service interrupted by user")
        except Exception as e:
            logger.error(f"Error starting Annotation service: {e}")
            raise
        finally:
            await self._cleanup()

    async def stop(self):
        """Stop the Annotation service gracefully."""
        logger.info("Stopping Annotation service...")
        self._stop_event.set()
        await self._cleanup()
        logger.info("Annotation service stopped successfully.")

    async def _cleanup(self):
        """Clean up resources."""
        try:
            if self.processor:
                await self.processor.stop()
            if self.service:
                await self.service.stop_monitoring()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status."""
        if not self.processor:
            return {'status': 'not_started', 'task_id': self.task_id}

        worker_status = self.processor.get_worker_status() if hasattr(self.processor, 'get_worker_status') else []
        return {
            'status': 'running' if self.processor.is_running else 'stopped',
            'task_id': self.task_id,
            'workers': worker_status,
            'service_monitoring': self.service is not None and getattr(self.service, 'is_running', False)
        }


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Annotation Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-id camera1
  %(prog)s --task-id warehouse_cam
  %(prog)s --task-id production --config custom_config.yaml
  
Topic naming:
  Frames input:     raw_frames_{task_id}
  Detections input: yolox_detections_{task_id}
  RTSP output:      outstream_{task_id}
        """
    )
    parser.add_argument('--config', type=str, default='dev_pose_estimation_config.yaml',
                        help='Path to configuration file')
    parser.add_argument('--task-id', type=str, required=True,
                        help='Task ID for dynamic topic generation (REQUIRED)')
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    try:
        service = AnnotationService(config_path=args.config, task_id=args.task_id)
        await service.start_service()

    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
