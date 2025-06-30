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

## Quick Start

TODO: Add setup and installation instructions

## API Endpoints

- `POST /upload` - Upload video file for processing
- `GET /status/{task_id}` - Check processing status
- `GET /result/{task_id}` - Get processed video output

## Development

TODO: Add development setup instructions

## Architecture Components

- **FastAPI Backend**: API endpoints and pipeline coordination
- **Kafka Broker**: Message passing between AI services  
- **YOLOX Service**: Human detection and bounding boxes
- **RTMPose Service**: Pose keypoint estimation
- **ByteTrack Service**: Multi-person tracking with persistent IDs
- **Annotation Service**: Video rendering and output streaming

## Configuration

Each service has its own configuration file in the respective `config.yaml` files.

## Testing

TODO: Add testing instructions

## Deployment

TODO: Add deployment instructions using Docker Compose

## Contributing

TODO: Add contribution guidelines 


## 🚧 Key TODOs Marked:

[ ] Model Loading: The actual model loading code is marked as TODO since it requires the specific model files and [ ] their respective libraries (YOLOX, MMPose, ByteTrack)
[ ] RTSP Streaming: The actual FFmpeg integration for RTSP streaming is marked as TODO
[ ] Frame Synchronization: Complete implementation of frame-pose synchronization in the annotation service
[ ] Health Checks: Service health monitoring endpoints
[ ] Completion Detection: Proper task completion detection based on Kafka message flow