# Dockerfile for FastAPI Backend Service
# Multi-stage build for optimal image size and security

# TODO: Implement multi-stage Docker build:
# Stage 1: Base Python runtime with system dependencies
# Stage 2: Install Python dependencies
# Stage 3: Copy application code and set up runtime user
# Final stage: Configure entrypoint and health checks

# TODO: Add the following features:
# - Non-root user for security
# - Health check endpoint configuration
# - Environment variable configuration
# - Volume mounts for uploads and outputs
# - Proper logging and signal handling 
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libgomp1 \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core/ ./core/
COPY apps/fastapi_backend/ ./apps/fastapi_backend/

# Create necessary directories
RUN mkdir -p /tmp/video_uploads /tmp/video_outputs

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command (can be overridden)
CMD ["uvicorn", "apps.fastapi_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]