#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

import torch
import yaml

from apps.annotation_service.annotation_worker import AnnotationWorker
from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.multi_input_interface import MultiInputInterface
from contanos.io.multi_output_interface import MultiOutputInterface
from contanos.io.rtsp_output_interface import RTSPOutput
from contanos.io.video_output_interface import VideoOutput
from contanos.utils.setup_logging import setup_logging

# Add project root for relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


class AnnotationService:
    """Annotation service: consumes frames, runs inference, outputs to RTSP and/or video file."""

    def __init__(self, config_path: str, task_id: str):
        if not task_id:
            raise ValueError("task_id is required")
        self.task_id = task_id
        self.config = self._load_config(config_path)

        # instance attributes for cleanup
        self.multi_input: MultiInputInterface = None  # type: ignore
        self.multi_output: MultiOutputInterface = None  # type: ignore
        self.processor = None
        self.service = None

        self.logger = logging.getLogger(__name__)
        self.logger.info(f"AnnotationService initialized (task_id={self.task_id})")

    def _load_config(self, path: str) -> Dict[str, Any]:
        """Load YAML config, searching multiple locations."""
        base = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            path,
            os.path.join(base, path),
            os.path.join(base, "..", path),
            os.path.join(os.getcwd(), path),
        ]
        for p in candidates:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        raise FileNotFoundError(f"Config not found in {candidates}")

    def _kafka_config(self, topic: str, group: str) -> Dict[str, Any]:
        kc = self.config.get('kafka', {})
        return {
            **kc,
            'topic': f"{topic}_{self.task_id}",
            'group_id': f"{group}_{self.task_id}",
        }

    def _rtsp_config(self) -> Dict[str, Any]:
        rtsp = self.config.get('rtsp', {})
        ann = self.config.get('annotation', {}).get('output', {})
        if ann.get('type') == 'rtsp':
            parts = ann.get('config', '').split(',')
            addr = parts[0] or rtsp.get('output_stream')
            cfg = {'addr': addr, 'topic': f"outstream_{self.task_id}"}
            for part in parts[1:]:
                if '=' in part:
                    k, v = part.split('=', 1)
                    if k in ('topic',):
                        cfg[k] = v.format(task_id=self.task_id)
                    elif k in ('width', 'height', 'fps'):
                        cfg[k] = int(v)
            return {**cfg,
                    'width': rtsp.get('output_width', 1920),
                    'height': rtsp.get('output_height', 1080),
                    'fps': rtsp.get('output_fps', 25)}
        return {
            'addr': rtsp.get('output_stream', 'rtsp://localhost:8554'),
            'topic': f"outstream_{self.task_id}",
            'width': rtsp.get('output_width', 1920),
            'height': rtsp.get('output_height', 1080),
            'fps': rtsp.get('output_fps', 25),
        }

    def _video_config(self) -> Dict[str, Any]:
        vcfg = self.config.get('annotation', {}).get('video_output', {})
        return {
            'task_id': self.task_id,
            'output_dir': vcfg.get('output_dir', 'output_videos'),
            'queue_max_len': vcfg.get('queue_max_len', 100),
            'filename_template': vcfg.get('filename_template', 'annotated_{task_id}_{timestamp}.mp4'),
            'width': vcfg.get('width', 1920),
            'height': vcfg.get('height', 1080),
            'fps': vcfg.get('fps', 25),
            'fourcc': vcfg.get('codec', 'mp4v'),
        }

    def _device_list(self) -> List[str]:
        dev = self.config.get('annotation', {}).get('devices', 'cpu')
        if isinstance(dev, str) and dev.lower() == 'cuda':
            return ['cuda'] if torch.cuda.is_available() else ['cpu']
        return dev if isinstance(dev, list) else [dev]

    def _processing_params(self) -> Dict[str, Any]:
        glob = self.config.get('global', {})
        return {
            'workers_per_device': glob.get('num_workers_per_device', 1),
            'health_check_interval': glob.get('health_check_interval', 5.0),
            'max_restart_attempts': glob.get('max_restart_attempts', 3),
            'restart_cooldown': glob.get('restart_cooldown', 3),
        }

    async def start_service(self):
        """Main entrypoint: initialize interfaces, start processing, and await termination."""
        setup_logging(self.config.get('global', {}).get('log_level', 'INFO'))
        self.logger.info("Starting AnnotationService...")

        # 1. Initialize inputs
        raw_cfg = self._kafka_config('raw_frames', 'annotation_raw')
        det_cfg = self._kafka_config('yolox_detections', 'annotation_track')
        pose_cfg = self._kafka_config('rtmpose_results', 'annotation_pose')
        self.multi_input = MultiInputInterface([
            KafkaInput(raw_cfg),
            KafkaInput(det_cfg),
            KafkaInput(pose_cfg),
        ])
        if not await self.multi_input.initialize():
            raise RuntimeError("Failed to initialize inputs")

        # 2. Initialize outputs
        outputs = [RTSPOutput(self._rtsp_config())]
        vcfg = self._video_config()
        if self.config.get('annotation', {}).get('video_output', {}).get('enabled', True):
            outputs.append(VideoOutput(vcfg))
            self.logger.info("Video output enabled")
        else:
            self.logger.info("Video output disabled")

        self.multi_output = MultiOutputInterface(outputs)
        if not await self.multi_output.initialize():
            raise RuntimeError("Failed to initialize outputs")

        # 3. Create processor & service
        devices = self._device_list()
        params = self._processing_params()
        model_cfg = {'debug_output_dir': self.config.get('annotation', {}).get('debug_output_dir', 'debug_frames'),
                     'video_output': self.config.get('annotation', {}).get('video_output', {}),
                     'task_id': self.task_id}
        workers, self.processor = create_a_processor(
            worker_class=AnnotationWorker,
            model_config=model_cfg,
            devices=devices,
            input_interface=self.multi_input,
            output_interface=self.multi_output,
            num_workers_per_device=params['workers_per_device']
        )
        self.logger.info(f"Spawned {len(workers)} workers on devices {devices}")

        self.service = BaseService(
            processor=self.processor,
            health_check_interval=params['health_check_interval'],
            max_restart_attempts=params['max_restart_attempts'],
            restart_cooldown=params['restart_cooldown'],
        )

        # 4. Run service within context managers
        try:
            async with self.service, self.processor:
                self.logger.info("Service is running. Press Ctrl+C to stop.")
                # wait until all workers finish or cancel
                while not all(t.done() for t in self.processor.worker_tasks):
                    await asyncio.sleep(1)
        except (asyncio.CancelledError, KeyboardInterrupt):
            self.logger.info("Shutdown signal received")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Ensure all components are properly shut down."""
        self.logger.info("Cleaning up AnnotationService...")
        tasks = []
        if self.processor:
            tasks.append(self.processor.stop())
        if self.service:
            tasks.append(self.service.stop_monitoring())
        if self.multi_input:
            tasks.append(self.multi_input.cleanup())
        if self.multi_output:
            tasks.append(self.multi_output.cleanup())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("Cleanup complete.")

    def get_service_status(self) -> Dict[str, Any]:
        """Return current status of service and workers."""
        if not self.processor:
            return {'status': 'not_started', 'task_id': self.task_id}
        return {
            'status': 'running' if getattr(self.processor, 'is_running', False) else 'stopped',
            'task_id': self.task_id,
            'workers': getattr(self.processor, 'get_worker_status', lambda: [])(),
            'monitoring': getattr(self.service, 'is_running', False),
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Annotation Service")
    parser.add_argument('--config', type=str, default='dev_pose_estimation_config.yaml')
    parser.add_argument('--task-id', required=True)
    return parser.parse_args()


async def main():
    args = parse_args()
    svc = AnnotationService(config_path=args.config, task_id=args.task_id)
    await svc.start_service()


if __name__ == "__main__":
    asyncio.run(main())
