"""
FastAPI backend for multi-user AI video analysis platform.
Refactored modular version.
"""
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Info as PrometheusInfo
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as instrumentator_metrics
from starlette.responses import FileResponse

from config import APP_TITLE, APP_VERSION, STATIC_DIR, CORS_SETTINGS, logger, FRONTEND_DIST_DIR, UPLOAD_DIR
from dependencies import initialize_services, cleanup_services
from routes.ai_services import router as ai_services_router
# Import all route modules
from routes.core import router as core_router
from routes.streams import router as streams_router
from routes.tasks import router as tasks_router
from routes.video import router as video_router
from routes.websocket_pose import router as websocket_pose_router


instrumentator: Optional[Instrumentator] = None
metrics_registered: bool = False
backend_info_metric: Optional[PrometheusInfo] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global instrumentator, metrics_registered, backend_info_metric

    logger.info("Starting AI Video Analysis Platform...")

    if instrumentator is None:
        instrumentator = Instrumentator()
        instrumentator.add(instrumentator_metrics.default())

        backend_info_metric = PrometheusInfo(
            "fastapi_backend_info",
            "Static metadata about the FastAPI backend service.",
        )

        from apps.fastapi_backend.metrics import (
            backend_active_tasks,
            backend_task_progress_percent,
            create_task_context,
        )

        default_context = create_task_context(task_id=None)
        default_labels = default_context.labels_for(None)
        backend_active_tasks.labels(**default_labels).set(0)
        backend_task_progress_percent.labels(**default_labels).set(0)

        def _record_backend_info(_: instrumentator_metrics.Info) -> None:
            if backend_info_metric is not None:
                backend_info_metric.info({"service_name": APP_TITLE})

        instrumentator.add(_record_backend_info)

    if backend_info_metric is not None:
        backend_info_metric.info({"service_name": APP_TITLE})

    if instrumentator is not None and not metrics_registered:
        instrumentator.instrument(app).expose(app, include_in_schema=False)
        metrics_registered = True

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

# Mount video files for direct access
app.mount("/media/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Mount output videos from annotation service
from pathlib import Path

ANNOTATION_OUTPUT_DIR = Path(__file__).parent.parent / "annotation_service" / "output_videos"
if ANNOTATION_OUTPUT_DIR.exists():
    app.mount("/media/outputs", StaticFiles(directory=str(ANNOTATION_OUTPUT_DIR), html=False), name="outputs")

# Mount SPA (if built)
frontend_built = FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "index.html").exists()
if frontend_built:
    logger.info(f"Frontend build found at: {FRONTEND_DIST_DIR}")

    # 挂载静态资源（JS, CSS, 图片等）
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/app/assets", StaticFiles(directory=str(assets_dir)), name="frontend_assets")


    # 处理 SPA 路由：所有 /app/* 路径都返回 index.html
    @app.get("/app/{path:path}")
    async def serve_spa(path: str):
        """服务 SPA 应用，支持客户端路由"""
        index_file = FRONTEND_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        else:
            logger.error(f"index.html not found at: {index_file}")
            return {"error": "Frontend not built"}


    @app.get("/app")
    async def serve_spa_root():
        """处理 /app 根路径"""
        return RedirectResponse(url="/app/")


    @app.get("/app/")
    async def serve_spa_index():
        """处理 /app/ 路径"""
        index_file = FRONTEND_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        else:
            logger.error(f"index.html not found at: {index_file}")
            return {"error": "Frontend not built"}
else:
    logger.warning(f"Frontend not built. Expected location: {FRONTEND_DIST_DIR}")
# Include all routers
app.include_router(core_router, tags=["core"])
app.include_router(video_router, tags=["video"])
app.include_router(tasks_router, tags=["tasks"])
app.include_router(streams_router, tags=["streams"])
app.include_router(ai_services_router, tags=["ai_services"])
app.include_router(websocket_pose_router, tags=["websocket_pose"])


# Redirect root to SPA if present
@app.get("/")
async def root_redirect():
    if FRONTEND_DIST_DIR.exists():
        return RedirectResponse(url="/app/")
    # Fallback to server-side dashboard route
    return RedirectResponse(url="/dashboard")


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
