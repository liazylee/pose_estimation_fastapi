# This file is now replaced by the common API router in contanos.ai_service.base_api
# The API endpoints are automatically created by create_ai_service_app()

# If you need YOLOX-specific endpoints, add them here:
from fastapi import APIRouter

# Create a router for any YOLOX-specific endpoints
yolox_router = APIRouter()

# Example of YOLOX-specific endpoint (if needed):
# @yolox_router.get("/yolox-specific-endpoint")
# async def yolox_specific_function():
#     return {"message": "YOLOX specific functionality"}

# The main router is created automatically by the base_api module
