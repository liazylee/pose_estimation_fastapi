#!/usr/bin/env python3
"""
Annotation service for drawing detection overlays and generating RTSP output.
Consumes raw_frames and yolox_detections from Kafka, renders annotations, and outputs to RTSP.
"""
import asyncio
import logging
import os
import sys
from typing import Dict, Any

import cv2
import numpy as np
import yaml

from contanos.io.multi_input_interface import MultiInputInterface

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from contanos.io.kafka_input_interface import KafkaInput
from contanos.io.rtsp_output_interface import RTSPOutput
from contanos.visualizer.box_drawer import draw_boxes_on_frame

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnnotationService:
    """Main annotation service class."""

    def __init__(self, config_path: str, task_id: str):
        self.config_path = config_path
        self.task_id = task_id
        self.config = self._load_config(self.config_path)

        # Initialize components
        self.multi_input_interface = None
        self.rtsp_output = None

        # Video file output
        self.video_writer = None
        self.video_output_enabled = False
        self.video_output_path = None

        # Processing state
        self.is_running = False
        self.frame_count = 0
        self.detection_count = 0

        logger.info(f"Initialized AnnotationService for task: {task_id}")

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

    def _get_kafka_input_config(self, topic_suffix: str, consumer_group: str) -> Dict[str, Any]:
        """Get Kafka input configuration for a specific topic."""
        kafka_config = self.config.get('kafka', {})
        bootstrap_servers = kafka_config.get('bootstrap_servers', 'localhost:9092')

        topic_template = kafka_config.get('topics', {}).get(topic_suffix, f"{topic_suffix}_{{task_id}}")
        topic = topic_template.format(task_id=self.task_id)

        consumer_group_template = kafka_config.get('consumer_groups', {}).get(consumer_group,
                                                                              f"{consumer_group}_{{task_id}}")
        group_id = consumer_group_template.format(task_id=self.task_id)

        consumer_settings = kafka_config.get('consumer', {})

        return {
            'bootstrap_servers': bootstrap_servers,
            'topic': topic,
            'group_id': group_id,
            'auto_offset_reset': consumer_settings.get('auto_offset_reset', 'latest'),
            'max_poll_records': consumer_settings.get('max_poll_records', 1),
            'consumer_timeout_ms': consumer_settings.get('consumer_timeout_ms', 1000),
            'enable_auto_commit': consumer_settings.get('enable_auto_commit', True)
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

        # Default configuration
        return {
            'addr': rtsp_config.get('output_stream', 'rtsp://localhost:8554'),
            'topic': f"outstream_{self.task_id}",
            'width': rtsp_config.get('output_width', 1920),
            'height': rtsp_config.get('output_height', 1080),
            'fps': rtsp_config.get('output_fps', 25)
        }

    def _ensure_frame_size(self, frame: np.ndarray) -> np.ndarray:
        """Ensure frame matches video output dimensions."""
        video_config = self._get_video_output_config()
        target_width = video_config.get('width', 1920)
        target_height = video_config.get('height', 1080)

        current_height, current_width = frame.shape[:2]

        if current_width != target_width or current_height != target_height:
            logger.debug(f"Resizing frame from {current_width}x{current_height} to {target_width}x{target_height}")
            frame = cv2.resize(frame, (target_width, target_height))

        return frame

    def _get_video_output_config(self) -> Dict[str, Any]:
        """Get video file output configuration."""
        annotation_config = self.config.get('annotation', {})
        video_config = annotation_config.get('video_output', {})

        if not video_config.get('enabled', True):  # Default to enabled
            return {'enabled': False}

        # Create output directory based on task_id
        base_dir = video_config.get('output_dir', 'output_videos')
        output_dir = os.path.join(base_dir, self.task_id)
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = video_config.get('filename_template', 'annotated_{task_id}_{timestamp}.mp4')
        filename = filename.format(task_id=self.task_id, timestamp=timestamp)
        output_path = os.path.join(output_dir, filename)

        return {
            'enabled': True,
            'output_path': output_path,
            'width': video_config.get('width', 1920),
            'height': video_config.get('height', 1080),
            'fps': video_config.get('fps', 25),
            'codec': video_config.get('codec', 'mp4v'),  # or 'XVID', 'H264'
            'quality': video_config.get('quality', 1.0)  # 0.0 to 1.0, lower = more compression
        }

    async def _initialize_inputs(self) -> None:
        """Initialize Kafka input interfaces using MultiInputInterface."""
        # Initialize raw frames input
        frame_config = self._get_kafka_input_config('raw_frames', 'annotation_raw')
        kafka_frame_input = KafkaInput(config=frame_config)
        logger.info(f"Configured frames input: {frame_config['topic']}")

        # Initialize detections input
        detection_config = self._get_kafka_input_config('yolox_output', 'annotation_track')
        kafka_detection_input = KafkaInput(config=detection_config)
        logger.info(f"Configured detections input: {detection_config['topic']}")

        # Initialize MultiInputInterface with all relevant inputs
        self.multi_input_interface = MultiInputInterface(interfaces=[
            kafka_frame_input,
            kafka_detection_input
        ])
        await self.multi_input_interface.initialize()
        logger.info("Initialized MultiInputInterface for annotation service")

    async def _initialize_output(self) -> None:
        """Initialize RTSP output interface."""
        rtsp_config = self._get_rtsp_output_config()
        self.rtsp_output = RTSPOutput(config=rtsp_config)
        await self.rtsp_output.initialize()
        logger.info(f"Initialized RTSP output: {rtsp_config['addr']}/{rtsp_config['topic']}")

    async def _initialize_video_output(self) -> None:
        """Initialize video file output."""
        video_config = self._get_video_output_config()

        if not video_config.get('enabled', False):
            logger.info("Video file output disabled")
            self.video_output_enabled = False
            return

        try:
            # Get video parameters
            width = video_config['width']
            height = video_config['height']
            fps = video_config['fps']
            codec = video_config['codec']
            output_path = video_config['output_path']

            # Create fourcc code for codec
            if codec.upper() == 'H264':
                fourcc = cv2.VideoWriter_fourcc(*'H264')
            elif codec.upper() == 'XVID':
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
            elif codec.upper() == 'MP4V':
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            else:
                logger.warning(f"Unknown codec '{codec}', using default 'mp4v'")
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')

            # Initialize VideoWriter
            self.video_writer = cv2.VideoWriter(
                output_path,
                fourcc,
                fps,
                (width, height)
            )

            if not self.video_writer.isOpened():
                raise Exception("Failed to open VideoWriter")

            self.video_output_enabled = True
            self.video_output_path = output_path

            logger.info(f"Video output initialized: {output_path}")
            logger.info(f"Video parameters: {width}x{height} @ {fps}fps, codec: {codec}")

        except Exception as e:
            logger.error(f"Failed to initialize video output: {e}")
            self.video_output_enabled = False

    async def _annotation_processor(self) -> None:
        """Process synchronized frames and detections."""
        logger.info("Starting annotation processor...")
        processed_count = 0

        while self.is_running:
            try:
                # Get synchronized pair
                logging.info(f"[DEBUG] Producer is waiting for data...")

                data_list, metadata_list = await self.multi_input_interface.read_data()
                logger.info(f'data_list,{data_list}')
                logger.info('=' * 30)
                logger.info(f'metadata_list,{metadata_list}')
                # Extract frame and detections
                frame = data_list[0]
                detections = data_list[1]

                # Process detections data
                if isinstance(detections, dict):
                    # Handle YOLOX result format
                    detection_list = detections.get('detections', [])
                elif isinstance(detections, list):
                    detection_list = detections
                else:
                    logger.warning(f"Unknown detection format: {type(detections)}")
                    detection_list = []

                frame_id = metadata_list[0].get('frame_id_str', 'unknown')
                logger.debug(f"Processing frame {frame_id}: {len(detection_list)} detections")
                # Draw annotations
                annotated_frame = self._draw_annotations(frame, detection_list)

                # Send to RTSP output
                await self._send_to_rtsp(annotated_frame)

                # Save to video file
                await self._save_to_video(annotated_frame)

                processed_count += 1
                if processed_count % 10 == 0:
                    logger.info(f"Processed {processed_count} annotated frames")

            except Exception as e:
                logger.error(f"Error in annotation processor: {e}")
                await asyncio.sleep(0.1)

    def _draw_annotations(self, frame: np.ndarray, detections: list) -> np.ndarray:
        """Draw annotations on the frame."""
        try:
            # Create a copy to avoid modifying the original frame
            annotated_frame = frame.copy()

            # Convert detections to the format expected by box_drawer
            formatted_detections = []
            for detection in detections:
                if isinstance(detection, dict):
                    bbox = detection.get('bbox', [])
                    confidence = detection.get('confidence', 0.0)
                    class_name = detection.get('class_name', 'unknown')
                    class_id = detection.get('class_id', 0)

                    if len(bbox) >= 4:
                        formatted_detection = {
                            'bbox': bbox,
                            'score': confidence,  # box_drawer expects 'score' field
                            'class_id': class_id,
                            'class_name': class_name,
                            'track_id': None  # No tracking info yet
                        }
                        formatted_detections.append(formatted_detection)

            # Draw boxes using the existing box_drawer function
            if formatted_detections:
                annotated_frame = draw_boxes_on_frame(
                    annotated_frame,
                    formatted_detections,
                    scale=1.0,
                    draw_labels=True
                )

            # Add frame info overlay

            return annotated_frame

        except Exception as e:
            logger.error(f"Error drawing annotations: {e}")
            return frame

    async def _send_to_rtsp(self, frame: np.ndarray) -> None:
        """Send annotated frame to RTSP output."""
        try:
            # Ensure frame size matches configuration
            frame = self._ensure_frame_size(frame)

            # Convert BGR to RGB for RTSP output
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Prepare data for RTSP output
            rtsp_data = {
                'results': {
                    'annotated_frame': rgb_frame
                }
            }

            await self.rtsp_output.write_data(rtsp_data)

        except Exception as e:
            logger.error(f"Error sending frame to RTSP: {e}")

    async def _save_to_video(self, frame: np.ndarray) -> None:
        """Save annotated frame to video file."""
        try:
            if self.video_output_enabled and self.video_writer:
                # Ensure frame size matches video writer configuration
                frame = self._ensure_frame_size(frame)

                # OpenCV VideoWriter expects BGR format
                self.video_writer.write(frame)

        except Exception as e:
            logger.error(f"Error saving frame to video: {e}")

    async def start(self) -> None:
        """Start the annotation service."""
        try:
            logger.info(f"Starting Annotation Service for task: {self.task_id}")

            # Initialize inputs and output
            await self._initialize_inputs()
            await self._initialize_output()
            await self._initialize_video_output()

            # Set running state
            self.is_running = True

            # Start all async tasks
            tasks = [
                asyncio.create_task(self._annotation_processor())
            ]

            logger.info("All tasks started. Press Ctrl+C to stop...")

            # Wait for all tasks
            await asyncio.gather(*tasks)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in annotation service: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the annotation service."""
        logger.info("Stopping annotation service...")

        self.is_running = False

        # Cleanup interfaces
        if self.multi_input_interface:
            await self.multi_input_interface.cleanup()

        if self.rtsp_output:
            await self.rtsp_output.cleanup()

        # Cleanup video output
        if self.video_writer:
            self.video_writer.release()
            logger.info(f"Video file saved: {self.video_output_path}")

        logger.info("Annotation service stopped")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Annotation Service')
    parser.add_argument('--task-id', required=True, help='Task ID')
    parser.add_argument('--config', default='dev_pose_estimation_config.yaml',
                        help='Configuration file path')

    args = parser.parse_args()

    # Create and start service
    service = AnnotationService(args.config, args.task_id)

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
