# This file is now replaced by the common API router in contanos.ai_service.base_api
# The API endpoints are automatically created by create_ai_service_app()

# If you need RTMPose-specific endpoints, add them here:
from fastapi import APIRouter

# Create a router for any RTMPose-specific endpoints
rtmpose_router = APIRouter()

# Example of RTMPose-specific endpoint (if needed):
# @rtmpose_router.get("/rtmpose-specific-endpoint")
# async def rtmpose_specific_function():
#     return {"message": "RTMPose specific functionality"}

# The main router is created automatically by the base_api module 