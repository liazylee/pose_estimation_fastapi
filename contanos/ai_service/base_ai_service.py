#!/usr/bin/env python3
"""
Abstract base class for AI services to eliminate code duplication.
Provides common functionality for all AI services including:
- Configuration loading
- Interface initialization
- Processor creation
- Service monitoring and lifecycle management
- Error handling and cleanup
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Type

import torch
import yaml

from contanos.base_service import BaseService
from contanos.helpers.create_a_processor import create_a_processor
from contanos.io.multi_input_interface import MultiInputInterface
from contanos.utils.setup_logging import setup_logging

logger = logging.getLogger(__name__)


class BaseAIService(ABC):
    """Abstract base class for AI services with common functionality."""

    def __init__(self, config_path: str = "dev_pose_estimation_config.yaml", task_id: str = None):
        if task_id is None:
            raise ValueError("task_id is required and cannot be None. Please specify a task_id.")

        self.task_id = task_id
        self.config = self._load_config(config_path)

        # Common instance variables
        self.processor = None
        self.service = None
        self.multi_input_interface = None
        self.output_interface = None
        self.input_interfaces = []  # Keep track of individual input interfaces

        logger.info(f"{self.get_service_name()} initialized with task_id: '{self.task_id}'")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file, searching multiple locations."""
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Common search paths for all services
        possible_paths = [
            config_path,  # Absolute path or relative to current working directory
            os.path.join(script_dir, config_path),  # Relative to service directory
            os.path.join(script_dir, "..", config_path),  # Relative to apps directory
            os.path.join(script_dir, "..", "..", config_path),  # Relative to project root
            os.path.join(script_dir, "..", "..", "..", config_path),  # Relative to contanos
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
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Successfully loaded configuration from: {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {config_file}: {e}")
            raise

    def _substitute_task_id(self, config_string: str) -> str:
        """Replace {task_id} placeholder in config strings."""
        return config_string.replace("{task_id}", self.task_id)

    def _get_devices(self) -> List[str]:
        """Get list of devices from configuration."""
        service_config = self.config.get(self.get_service_config_key(), {})
        global_config = self.config.get('global', {})

        device_config = service_config.get('devices') or global_config.get('devices', 'cpu')

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

    def _get_processing_config(self) -> Dict[str, Any]:
        """Get common processing configuration."""
        global_config = self.config.get('global', {})

        return {
            'workers_per_device': global_config.get('num_workers_per_device', 1),
            'health_check_interval': global_config.get('health_check_interval', 5.0),
            'max_restart_attempts': global_config.get('max_restart_attempts', 3),
            'restart_cooldown': global_config.get('restart_cooldown', 3)
        }
    
    def _get_sync_config(self) -> Dict[str, Any]:
        """Get synchronization configuration for MultiInputInterface."""
        service_config = self.config.get(self.get_service_config_key(), {})
        sync_config = service_config.get('input_sync_config', {})
        
        # Default values optimized for large video processing
        return {
            'frame_timeout_sec': sync_config.get('frame_timeout_sec', 30),
            'sync_mode': sync_config.get('sync_mode', 'adaptive'), 
            'max_memory_mb': sync_config.get('max_memory_mb', 512),
            'enable_backpressure_monitoring': sync_config.get('enable_backpressure_monitoring', True)
        }

    async def _initialize_interfaces(self):
        """Initialize input and output interfaces."""
        # Create input interfaces
        input_interfaces = self.create_input_interfaces()
        self.input_interfaces = input_interfaces

        # Create MultiInputInterface with default settings (恢复原始逻辑)
        self.multi_input_interface = MultiInputInterface(
            interfaces=input_interfaces,
            metrics_service=self.get_service_name(),
            metrics_task_id=self.task_id,
        )
        await self.multi_input_interface.initialize()

        # Create output interface
        self.output_interface = self.create_output_interface()
        await self.output_interface.initialize()

        logger.info(f"Initialized {len(input_interfaces)} input interfaces and output interface")

    async def _create_processor(self):
        """Create processor with workers."""
        devices = self._get_devices()
        model_config = dict(self.get_model_config())
        model_config.setdefault('task_id', self.task_id)
        model_config.setdefault('service_name', self.get_service_name())
        if self.output_interface and hasattr(self.output_interface, 'topic'):
            model_config.setdefault('output_topic', getattr(self.output_interface, 'topic', 'unknown'))
        processing_config = self._get_processing_config()

        logger.info(f"Using devices: {devices}")
        logger.info(f"Model config: {model_config}")

        # Create processor with workers
        workers, self.processor = create_a_processor(
            worker_class=self.get_worker_class(),
            model_config=model_config,
            devices=devices,
            input_interface=self.multi_input_interface,
            output_interface=self.output_interface,
            num_workers_per_device=processing_config['workers_per_device']
        )

        logger.info(f"Created {len(workers)} workers across {len(devices)} devices")
        return processing_config

    async def _create_service(self, processing_config: Dict[str, Any]):
        """Create and configure the service monitor."""
        self.service = BaseService(
            processor=self.processor,
            health_check_interval=processing_config['health_check_interval'],
            max_restart_attempts=processing_config['max_restart_attempts'],
            restart_cooldown=processing_config['restart_cooldown']
        )

    async def start_service(self):
        """Start the AI service using contanos framework."""
        try:
            # Setup logging
            global_config = self.config.get('global', {})
            log_level = global_config.get('log_level', 'INFO')
            setup_logging(log_level)
            logger.info(f"Starting {self.get_service_name()} with contanos framework for task: {self.task_id}")

            # Initialize interfaces
            await self._initialize_interfaces()

            # Create processor
            processing_config = await self._create_processor()

            # Create service
            await self._create_service(processing_config)

            # Start service
            async with self.service:
                async with self.processor:
                    logger.info(f"{self.get_service_name()} started successfully for task: {self.task_id}")
                    logger.info("Service is running. Press Ctrl+C to stop.")

                    # Keep running until interrupted or completed
                    await self._run_loop()

        except Exception as e:
            logger.error(f"Error starting {self.get_service_name()}: {e}")
            raise
        finally:
            await self._cleanup()

    async def _run_loop(self):
        """Main service run loop. Can be overridden by subclasses."""
        try:
            # Wait until all workers finish or cancel
            while not all(task.done() for task in self.processor.worker_tasks):
                await asyncio.sleep(1)
        # Handle graceful shutdown

        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Shutdown signal received")
            raise
        except Exception as e:
            logger.error(f"Error during service run loop: {e}")
            raise

    async def _cleanup(self):
        """Clean up all resources."""
        logger.info(f"Cleaning up {self.get_service_name()}...")
        try:
            cleanup_tasks = []

            if self.multi_input_interface:
                cleanup_tasks.append(self.multi_input_interface.cleanup())

            if self.output_interface:
                cleanup_tasks.append(self.output_interface.cleanup())

            # Additional cleanup for specific interfaces
            for interface in self.input_interfaces:
                if hasattr(interface, 'cleanup'):
                    cleanup_tasks.append(interface.cleanup())

            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)

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

    # Abstract methods that subclasses must implement
    @abstractmethod
    def get_service_name(self) -> str:
        """Return the name of the service (e.g., 'YOLOX Service')."""
        pass

    @abstractmethod
    def get_service_config_key(self) -> str:
        """Return the configuration key for this service (e.g., 'yolox', 'rtmpose')."""
        pass

    @abstractmethod
    def get_worker_class(self) -> Type:
        """Return the worker class for this service."""
        pass

    @abstractmethod
    def create_input_interfaces(self) -> List[Any]:
        """Create and return list of input interfaces."""
        pass

    @abstractmethod
    def create_output_interface(self) -> Any:
        """Create and return the output interface."""
        pass

    @abstractmethod
    def get_model_config(self) -> Dict[str, Any]:
        """Return model configuration for this service."""
        pass

    # Optional methods that can be overridden
    def validate_config(self):
        """Validate service-specific configuration. Override if needed."""
        pass

    def setup_additional_logging(self):
        """Setup additional logging configuration. Override if needed."""
        pass
