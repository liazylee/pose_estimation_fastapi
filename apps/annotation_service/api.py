# This file is now replaced by the common API router in contanos.ai_service.base_api
# The API endpoints are automatically created by create_ai_service_app()

# If you need Annotation-specific endpoints, add them here:
from fastapi import APIRouter

# Create a router for any Annotation-specific endpoints
annotation_router = APIRouter()

# Example of Annotation-specific endpoint (if needed):
# @annotation_router.get("/annotation-specific-endpoint")
# async def annotation_specific_function():
#     return {"message": "Annotation specific functionality"}

# The main router is created automatically by the base_api module
