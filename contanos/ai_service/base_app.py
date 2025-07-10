import argparse
import logging
from contextlib import asynccontextmanager
from typing import Callable

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .base_api import create_api_router
from .models import HealthSummary
from .service_config import ServiceConfig


def create_ai_service_app(config: ServiceConfig, service_manager_getter: Callable):
    """Create a FastAPI application for an AI service with common setup."""
    
    # lifespan context manager
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.info(f"{config.service_name} Starting (lifespan startup)...")
        manager = service_manager_getter()
        manager._start_monitoring()
        yield  # App is running here
        logging.info(f"{config.service_name} Shutting Down (lifespan shutdown)...")
        await manager.cleanup_all()

    app = FastAPI(
        title=config.service_name,
        description=config.service_description,
        version=config.service_version,
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create and include the API router
    api_router = create_api_router(service_manager_getter, config)
    app.include_router(api_router)

    @app.get("/health", response_model=HealthSummary)
    async def health_check():
        manager = service_manager_getter()
        health_summary = manager.get_health_summary()
        return HealthSummary(**health_summary)

    return app


def run_ai_service_app(app: FastAPI, config: ServiceConfig):
    """Run the AI service app with command line argument parsing."""
    parser = argparse.ArgumentParser(description=config.service_description)
    parser.add_argument("--host", default=config.default_host, help="Host to bind to")
    parser.add_argument("--port", type=int, default=config.default_port, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload
    ) 