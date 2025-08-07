"""
FastAPI backend for multi-user AI video analysis platform.
Refactored modular version.
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import APP_TITLE, APP_VERSION, STATIC_DIR, CORS_SETTINGS, logger
from dependencies import initialize_services, cleanup_services
from routes.ai_services import router as ai_services_router
# Import all route modules
from routes.core import router as core_router
from routes.streams import router as streams_router
from routes.tasks import router as tasks_router
from routes.video import router as video_router
from routes.websocket_pose import router as websocket_pose_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting AI Video Analysis Platform...")

    # Initialize all services
    await initialize_services()

    yield

    logger.info("Shutting down AI Video Analysis Platform...")

    # Cleanup all services
    await cleanup_services()


# Initialize FastAPI app
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(CORSMiddleware, **CORS_SETTINGS)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include all routers
app.include_router(core_router, tags=["core"])
app.include_router(video_router, tags=["video"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(streams_router, tags=["streams"])
app.include_router(ai_services_router, tags=["ai_services"])
app.include_router(websocket_pose_router, tags=["websocket_pose"])

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Analysis controller backend")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
