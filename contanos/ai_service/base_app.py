import argparse
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Info as PrometheusInfo
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as instrumentator_metrics

from .base_api import create_api_router
from .models import HealthSummary
from .service_config import ServiceConfig


def create_ai_service_app(config: ServiceConfig, service_manager_getter: Callable):
    """Create a FastAPI application for an AI service with common setup."""
    
    # lifespan context manager
    instrumentator: Optional[Instrumentator] = None
    metrics_registered = False
    service_info_metric: Optional[PrometheusInfo] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal instrumentator, metrics_registered, service_info_metric

        logging.info(f"{config.service_name} Starting (lifespan startup)...")

        if instrumentator is None:
            instrumentator = Instrumentator()
            instrumentator.add(instrumentator_metrics.default())

            service_info_metric = PrometheusInfo(
                "ai_service_info",
                "Static metadata about the AI microservice.",
            )

            def _record_service_info(_: instrumentator_metrics.Info) -> None:
                if service_info_metric is not None:
                    service_info_metric.info({"service_name": config.service_name})

            instrumentator.add(_record_service_info)

        if service_info_metric is not None:
            service_info_metric.info({"service_name": config.service_name})

        if instrumentator is not None and not metrics_registered:
            instrumentator.instrument(app).expose(app, include_in_schema=False)
            metrics_registered = True

        manager = service_manager_getter()
        manager._start_monitoring()

        try:
            yield  # App is running here
        finally:
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