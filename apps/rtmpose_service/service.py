#!/usr/bin/env python3
"""
Refactored RTMPose service using BaseAIService to eliminate code duplication.
Only contains RTMPose-specific configuration and logic.
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

# Import RTMPoseWorker with error handling for different execution contexts
try:
    from .rtmpose_worker import RTMPoseWorker
except ImportError:
    try:
        from rtmpose_worker import RTMPoseWorker
    except ImportError:
        from apps.rtmpose_service.rtmpose_worker import RTMPoseWorker

logger = logging.getLogger(__name__)


class RTMPoseService(BaseAIService):
    """RTMPose estimation service using BaseAIService framework."""

    def get_service_name(self) -> str:
        return "RTMPose Service"

    def get_service_config_key(self) -> str:
        return "rtmpose"

    def get_worker_class(self):
        return RTMPoseWorker

    def create_input_interfaces(self) -> List[KafkaInput]:
        """Create Kafka input interfaces for frames and detections."""
        frames_config = self._get_kafka_input_config('raw_frames', 'rtmpose_raw')
        detections_config = self._get_kafka_input_config('bytetrack_tracking', 'rtmpose_det')

        logger.info(f"Frames input topic: {frames_config.get('topic')}")
        logger.info(f"Detections input topic: {detections_config.get('topic')}")

        return [
            KafkaInput(config=frames_config),
            KafkaInput(config=detections_config)
        ]

    def create_output_interface(self) -> KafkaOutput:
        """Create Kafka output interface for pose results."""
        output_config = self._get_kafka_output_config()
        logger.info(f"Output topic: {output_config.get('topic')}")

        return KafkaOutput(config=output_config)

    def get_model_config(self) -> Dict[str, Any]:
        """Get RTMPose model configuration."""
        rtmpose_config = self.config.get('rtmpose', {})
        global_config = self.config.get('global', {})

        return {
            'onnx_model': rtmpose_config.get('onnx_model'),
            'model_input_size': rtmpose_config.get('model_input_size'),
            'backend': rtmpose_config.get('backend') or global_config.get('backend', 'onnxruntime')
        }

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


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="RTMPose Service (Refactored)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-id camera1
  %(prog)s --task-id warehouse_cam --config custom_config.yaml
  
Topic naming:
  Input topics:     raw_frames_{task_id}, yolox_detections_{task_id}
  Output topic:     rtmpose_results_{task_id}
  Consumer groups:  rtmpose_raw_{task_id}, rtmpose_det_{task_id}
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
        service = RTMPoseService(config_path=args.config, task_id=args.task_id)

        # Override config with command line arguments if provided
        if args.devices:
            device_list = args.devices.split(',')
            service.config.setdefault('rtmpose', {})['devices'] = device_list
            logger.info(f"Overriding devices with: {device_list}")

        await service.start_service()

    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
