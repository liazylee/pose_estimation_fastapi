# Dockerfile for YOLOX Detection Service
# Optimized for computer vision and GPU acceleration

# TODO: Implement Docker build for YOLOX service:
# - Base image with CUDA support (nvidia/cuda or pytorch/pytorch)
# - Install OpenCV, PyTorch, and YOLOX dependencies
# - Copy model weights and configuration files
# - Set up proper GPU device access
# - Configure service entrypoint and monitoring

# TODO: Add optimization features:
# - Multi-architecture support (CPU/GPU)
# - Model weight caching and optimization
# - Memory usage monitoring and limits
# - Graceful shutdown handling 
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install YOLOX
# TODO: Add actual YOLOX installation
# RUN git clone https://github.com/Megvii-BaseDetection/YOLOX.git /tmp/yolox && \
#     cd /tmp/yolox && \
#     pip install -v -e . && \
#     rm -rf /tmp/yolox/.git

# Copy application code
COPY core/ ./core/
COPY apps/yolox_service/ ./apps/yolox_service/

# Create model directory
RUN mkdir -p /models

# Set Python path
ENV PYTHONPATH=/app

# Default command
CMD ["python", "-m", "apps.yolox_service.service"]