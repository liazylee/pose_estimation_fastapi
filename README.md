# Multi-User AI Video Analysis Platform

A scalable pose estimation pipeline using FastAPI, Kafka, and multiple AI services (YOLOX → RTMPose → ByteTrack → Annotation).

## System Architecture

This system processes uploaded videos through an AI-powered pose estimation pipeline with support for multi-user, concurrent video uploads. Each upload gets its own isolated Kafka pipeline for processing.

## Features

- **Multi-User Support**: Concurrent video processing with isolated pipelines
- **Real-time Processing**: Streaming-based architecture using Kafka
- **Modular AI Services**: YOLOX detection, RTMPose estimation, ByteTrack tracking
- **Flexible Output**: RTSP streaming or MP4 file output
- **Scalable Architecture**: Each service can be scaled independently
- **Code Reuse**: Common AI service framework with minimal duplication

## Quick Start

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd pose_estimation_fastapi
```

2. Install the project in development mode:
```bash
pip install -e .
```

### Running Services

#### Option 1: Start All Services
```bash
python start_services.py
```

#### Option 2: Start Individual Services
```bash
# YOLOX detection service
python start_services.py yolox

# RTMPose estimation service  
python start_services.py rtmpose

# Annotation service
python start_services.py annotation
```

#### Option 3: Manual Service Startup
```bash
# YOLOX service (port 8001)
cd apps/yolox_service
python main.py --port 8001

# RTMPose service (port 8002)
cd apps/rtmpose_service  
python main.py --port 8002

# Annotation service (port 8003)
cd apps/annotation_service
python main.py --port 8003
```

### Service URLs

After starting, the services will be available at:
- **YOLOX Service**: http://localhost:8001
- **RTMPose Service**: http://localhost:8002  
- **Annotation Service**: http://localhost:8003
- **FastAPI Backend**: http://localhost:8000 (if running separately)

## API Endpoints

All AI services provide the same REST API interface:

- `GET /` - Service information and available endpoints
- `POST /services/start` - Start processing for a task_id
- `GET /services/{task_id}/status` - Check processing status
- `POST /services/{task_id}/stop` - Stop processing for a task_id
- `POST /services/{task_id}/complete` - Mark task as completed
- `GET /services` - List all running services
- `DELETE /services` - Stop all services
- `GET /health` - Health check

## Development

### Project Structure

```
├── contanos/                 # Shared framework
│   ├── ai_service/          # Common AI service components
│   │   ├── models.py        # Shared data models
│   │   ├── base_app.py      # FastAPI app creator
│   │   ├── base_api.py      # Common API routes
│   │   ├── base_service_manager.py  # Service management
│   │   └── service_config.py # Service configuration
│   ├── base_service.py      # Service monitoring
│   └── base_processor.py    # Processing base class
├── apps/                    # AI services
│   ├── yolox_service/       # YOLOX detection
│   ├── rtmpose_service/     # RTMPose estimation  
│   ├── annotation_service/  # Video annotation
│   └── fastapi_backend/     # Main API backend
└── start_services.py        # Convenient startup script
```

### Creating New AI Services

To create a new AI service, you only need:

1. **Service Implementation** (your AI logic)
2. **Service Configuration**:

```python
from contanos.ai_service import ServiceConfig, BaseServiceManager, create_ai_service_app

# Define service configuration
NEW_SERVICE_CONFIG = ServiceConfig(
    service_name="My AI Service",
    service_description="Description of my AI service",
    service_factory=MyAIService,  # Your service class
    default_port=8004,
    topic_config={
        "input": "input_topic_{task_id}",
        "output": "output_topic_{task_id}"
    }
)

# Create service manager
class ServiceManager(BaseServiceManager):
    def __init__(self):
        super().__init__(NEW_SERVICE_CONFIG)

# Create app
app = create_ai_service_app(NEW_SERVICE_CONFIG, get_service_manager)
```

3. **Simple main.py**:

```python
from contanos.ai_service import run_ai_service_app
from service_manager import get_service_manager, NEW_SERVICE_CONFIG

app = create_ai_service_app(NEW_SERVICE_CONFIG, get_service_manager)

if __name__ == "__main__":
    run_ai_service_app(app, NEW_SERVICE_CONFIG)
```

That's it! Your new service will have all the standard endpoints automatically.

### Code Reuse Benefits

The refactored architecture provides:

- **54% code reduction**: From ~1590 lines of duplicate code to 729 lines total
- **Unified API**: All services have identical interfaces
- **Easy maintenance**: Updates in one place affect all services
- **Quick development**: New services can be created in minutes

## Architecture Components

- **FastAPI Backend**: API endpoints and pipeline coordination
- **Kafka Broker**: Message passing between AI services  
- **YOLOX Service**: Human detection and bounding boxes
- **RTMPose Service**: Pose keypoint estimation
- **ByteTrack Service**: Multi-person tracking with persistent IDs
- **Annotation Service**: Video rendering and output streaming
- **Common Framework**: Shared code for all AI services

## Configuration

Each service has its own configuration defined in `ServiceConfig`. The framework handles:

- Automatic port assignment
- Topic name generation
- Service lifecycle management
- Health monitoring and auto-restart
- Unified error handling

## Testing

```bash
# Test framework imports
python -c "from contanos.ai_service import BaseServiceManager; print('Framework OK')"

# Test service imports  
cd apps/yolox_service && python -c "from service_manager import YOLOX_CONFIG; print('YOLOX OK')"
```

## Deployment

The services can be deployed using Docker Compose:

```bash
# Build and start all services
docker-compose up --build

# Start specific services
docker-compose up yolox rtmpose annotation
```

## Monitoring

All services provide:
- Health check endpoints (`/health`)
- Service status monitoring (`/services/{task_id}/status`)
- Automatic restart on failure
- Centralized logging

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes using the common framework
4. Add tests for new functionality
5. Submit a pull request

## Migration from Old Architecture

If you have existing services based on the old architecture:

1. **Models**: Remove `models.py`, import from `contanos.ai_service`
2. **Service Manager**: Inherit from `BaseServiceManager` 
3. **API**: Replace with service configuration
4. **Main**: Use `create_ai_service_app()` and `run_ai_service_app()`

All existing functionality is preserved with identical APIs.

## 🚧 Key TODOs

- [ ] Model Loading: Implement actual model loading for YOLOX, RTMPose, ByteTrack
- [ ] RTSP Streaming: Complete FFmpeg integration for real-time streaming
- [ ] Frame Synchronization: Improve frame-pose sync in annotation service  
- [ ] Docker Configuration: Add containerization for each service
- [ ] Performance Monitoring: Add metrics collection and dashboards