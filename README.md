# Multi-User AI Video Analysis Platform

This project provides a modular pose estimation pipeline built with **FastAPI** and **Kafka**. Video uploads are processed through a chain of AI services (YOLOX → RTMPose → ByteTrack → Annotation) and each user task is isolated on its own Kafka topics for easy scaling.

## Features

- **Multi-User Support** – concurrent video processing with isolated pipelines
- **Real-time Processing** – streaming architecture via Kafka
- **Modular AI Services** – detection, pose estimation, tracking and annotation
- **Flexible Output** – RTSP streaming or MP4 file export
- **Scalable Architecture** – each service can run independently
- **Code Reuse** – common framework under `contanos/`

## Quick Start

### Installation

1. Clone the repository
   ```bash
   git clone <your-repo-url>
   cd pose_estimation_fastapi
   ```
2. Install the project in development mode
   ```bash
   pip install -e .
   ```

### Running Services

Kafka, Zookeeper and an RTSP server are defined in `docker/compose.yaml`:

```bash
docker compose up -d
```

Start all AI services at once:

```bash
python start_services.py
```

To run a single service:

```bash
python start_services.py yolox       # or rtmpose / annotation
```

The services will be available at:

- **YOLOX** – http://localhost:8001
- **RTMPose** – http://localhost:8002
- **Annotation** – http://localhost:8003
- **FastAPI Backend** – http://localhost:8000

## Documentation

The repository includes several markdown documents detailing the design:

- `01_system_architecture.md` – system overview and component diagram
- `02_message_shemas.md` – Kafka message definitions
- `03_model_service_interface.md` – AI model service API
- `04_fastapi_pipeline_controller.md` – FastAPI backend controller
- `05_kafka_managenmant.md` – Kafka topic lifecycle management

## Running Tests

Install the development dependencies and run:

```bash
pytest -q
```

(Some unit tests require Kafka and heavy model downloads.)

## Contributing

1. Fork the repository and create a feature branch
2. Make your changes using the shared framework
3. Add tests for new functionality
4. Submit a pull request

See `TODO.md` for planned improvements.
