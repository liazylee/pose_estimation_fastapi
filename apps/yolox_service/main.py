import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from models import HealthSummary

from api import router as api_router
from service_manager import get_service_manager

logger = logging.getLogger(__name__)


# 新的 lifespan 写法
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("YOLOX Service Starting (lifespan startup)...")
    manager = get_service_manager()
    manager._start_monitoring()
    yield  # App is running here
    logger.info("YOLOX Service Shutting Down (lifespan shutdown)...")
    await manager.cleanup_all()


app = FastAPI(
    title="YOLOX Detection Service",
    description="Microservice for YOLOX object detection with dynamic task_id support",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", response_model=HealthSummary)
async def health_check():
    manager = get_service_manager()
    health_summary = manager.get_health_summary()
    return HealthSummary(**health_summary)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YOLOX Detection Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
