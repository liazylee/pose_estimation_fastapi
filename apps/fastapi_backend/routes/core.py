"""
Core routes for the FastAPI application.
Includes dashboard, API root, and health check endpoints.
"""
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from config import TEMPLATES_DIR, APP_VERSION
from dependencies import get_ai_orchestrator

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    html_file = TEMPLATES_DIR / "dashboard.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(), status_code=200)
    else:
        return HTMLResponse(
            content="""
            <html>
                <head><title>AI Video Analysis Platform</title></head>
                <body>
                    <h1>AI Video Analysis Platform</h1>
                    <p>Dashboard is being set up...</p>
                    <p>API endpoints:</p>
                    <ul>
                        <li>POST /upload - Upload video file</li>
                        <li>GET /status/{task_id} - Check task status</li>
                        <li>GET /result/{task_id} - Get result</li>
                        <li>GET /health - Health check</li>
                        <li>GET /api/files - List uploaded files</li>
                    </ul>
                </body>
            </html>
            """,
            status_code=200
        )


@router.get("/api")
async def api_root():
    """API root endpoint."""
    return {
        "message": "AI Video Analysis Platform API",
        "version": APP_VERSION,
        "endpoints": {
            "upload": "/upload",
            "status": "/status/{task_id}",
            "result": "/result/{task_id}",
            "health": "/health",
            "files": "/api/files",
            "tasks": "/api/tasks",
            "streams": "/streams",
            "streams/{task_id}/stop": "/streams/{task_id}/stop",
            "streams/{task_id}/status": "/streams/{task_id}/status",
            # AI Service Management
            "ai_start_pipeline": "/api/ai/pipeline/start",
            "ai_stop_pipeline": "/api/ai/pipeline/{task_id}/stop",
            "ai_pipeline_status": "/api/ai/pipeline/{task_id}/status",
            "ai_health": "/api/ai/health",
            "yolox_services": "/api/ai/yolox/services",
            "yolox_service_status": "/api/ai/yolox/{task_id}/status"
        }
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    ai_orchestrator = get_ai_orchestrator()
    
    # Get AI services health
    ai_health = await ai_orchestrator.health_check()

    return {
        "status": "healthy" if ai_health["overall_healthy"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "kafka": "TODO: Check Kafka connection",
            "rtmpose": ai_health["services"].get("rtmpose", {}).get("status", "unknown"),
            "bytetrack": ai_health["services"].get("bytetrack", {}).get("status", "unknown"),
            "annotation": ai_health["services"].get("annotation", {}).get("status", "unknown"),
            "yolox": ai_health["services"].get("yolox", {})
        },
        "ai_services_summary": ai_health
    } 