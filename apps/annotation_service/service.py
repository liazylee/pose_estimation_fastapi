#!/usr/bin/env python3
"""
Refactored Annotation service using BaseAIService to eliminate code duplication.
Only contains Annotation-specific configuration and logic.
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Dict, Any, List

import torch

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.ai_service import BaseAIService
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.multi_output_interface import MultiOutputInterface
from contanos.io.rtsp_output_interface import RTSPOutput
from contanos.io.video_output_interface import VideoOutput

# Import AnnotationWorker
try:
    from .annotation_worker import AnnotationWorker
except ImportError:
    try:
        from annotation_worker import AnnotationWorker
    except ImportError:
        from apps.annotation_service.annotation_worker import AnnotationWorker

logger = logging.getLogger(__name__)


class AnnotationService(BaseAIService):
    """Annotation service using BaseAIService framework."""

    def get_service_name(self) -> str:
        return "Annotation Service"

    def get_service_config_key(self) -> str:
        return "annotation"

    def get_worker_class(self):
        return AnnotationWorker

    def create_input_interfaces(self) -> List[KafkaInput]:
        """Create Kafka input interfaces for frames, detections, poses, and tracking."""
        raw_config = self._kafka_config('raw_frames', 'annotation_raw')
        det_config = self._kafka_config('yolox_detections', 'annotation_det')
        pose_config = self._kafka_config('rtmpose_results', 'annotation_pose')
        track_config = self._kafka_config('bytetrack_tracking', 'annotation_track')

        logger.info(f"Raw frames topic: {raw_config.get('topic')}")
        logger.info(f"Detections topic: {det_config.get('topic')}")
        logger.info(f"Poses topic: {pose_config.get('topic')}")
        logger.info(f"Tracking topic: {track_config.get('topic')}")

        return [
            KafkaInput(raw_config),
            KafkaInput(det_config),
            KafkaInput(pose_config),
            KafkaInput(track_config)
        ]

    def create_output_interface(self) -> MultiOutputInterface:
        """Create multi-output interface for RTSP and video outputs."""
        outputs = [RTSPOutput(self._rtsp_config())]

        # Add video output if enabled
        video_config = self._video_config()
        if self.config.get('annotation', {}).get('video_output', {}).get('enabled', True):
            outputs.append(VideoOutput(video_config))
            logger.info("Video output enabled")
        else:
            logger.info("Video output disabled")

        return MultiOutputInterface(outputs)

    def get_model_config(self) -> Dict[str, Any]:
        """Get Annotation model configuration."""
        return {
            'debug_output_dir': self.config.get('annotation', {}).get('debug_output_dir', 'debug_frames'),
            'video_output': self.config.get('annotation', {}).get('video_output', {}),
            'task_id': self.task_id
        }

    def _kafka_config(self, topic: str, group: str) -> Dict[str, Any]:
        """Generate Kafka configuration for a topic and group."""
        kafka_config = self.config.get('kafka', {})
        return {
            **kafka_config,
            'topic': f"{topic}_{self.task_id}",
            'group_id': f"{group}_{self.task_id}",
        }

    def _rtsp_config(self) -> Dict[str, Any]:
        """Generate RTSP output configuration."""
        annotation_config = self.config.get('annotation', {}).get('output', {})

        config = {
            'addr': 'rtsp://localhost:8554',
            'topic': f"outstream_{self.task_id}",
            'width': 1920,
            'height': 1080,
            'fps': 25,
            'bitrate': '4000k',
            'preset': 'fast',
            'codec': 'h264_nvenc',
            'pixel_format': 'yuv420p',
        }
        if annotation_config.get('type') == 'rtsp':
            parts = annotation_config.get('config', '').split(',')
            if parts:
                config['addr'] = parts[0]
            for part in parts[1:]:
                if '=' in part:
                    key, value = part.split('=', 1)
                    if key == 'topic':
                        config[key] = value.format(task_id=self.task_id)
                    elif key in ('width', 'height', 'fps'):
                        config[key] = int(value)
            for key, value in annotation_config.items():
                if key not in ['type', 'config']:
                    config[key] = value
        return config

    def _video_config(self) -> Dict[str, Any]:
        """Generate video output configuration."""
        video_config = self.config.get('annotation', {}).get('video_output', {})
        # 默认fps设置为原视频fps，如果没有则使用25
        default_fps = video_config.get('fps', 25)
        
        return {
            'task_id': self.task_id,
            'output_dir': video_config.get('output_dir', 'output_videos'),
            'queue_max_len': video_config.get('queue_max_len', 100),
            'filename_template': video_config.get('filename_template', 'annotated_{task_id}_{timestamp}.mp4'),
            'width': video_config.get('width', 1920),
            'height': video_config.get('height', 1080),
            'fps': default_fps,  # 注意：应该从输入视频获取真实fps
            'fourcc': video_config.get('codec', 'mp4v'),
        }

    def _get_devices(self) -> List[str]:
        """Override device detection for annotation service."""
        annotation_config = self.config.get('annotation', {})
        global_config = self.config.get('global', {})

        device_config = annotation_config.get('devices') or global_config.get('devices', 'cpu')

        if isinstance(device_config, str) and device_config.lower() == 'cuda':
            return ['cuda'] if torch.cuda.is_available() else ['cpu']
        return device_config if isinstance(device_config, list) else [device_config]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Annotation Service (Refactored)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-id camera1
  %(prog)s --task-id warehouse_cam --config custom_config.yaml
  
Topic naming:
  Input topics:     raw_frames_{task_id}, yolox_detections_{task_id}, rtmpose_results_{task_id}
  Consumer groups:  annotation_raw_{task_id}, annotation_track_{task_id}, annotation_pose_{task_id}
  Output:          RTSP stream and/or video file
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
