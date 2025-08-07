### FastAPI Backend (Orchestrator & Dashboard)

Purpose
- Web backend to orchestrate AI microservices and provide a dashboard/UI
- Manages Kafka topics, starts/stops per-task services, exposes results

Key files
- `main.py`: App entry (default port 8000)
- `routes/`: Feature routes (core, video, tasks, streams, ai_services, websocket_pose)
- `ai_service_client.py`: Clients to YOLOX/RTMPose/ByteTrack/Annotation management APIs
- `kafka_controller.py`: Creates/deletes Kafka topics per task
- `templates/`, `static/`: Simple dashboard assets
- `config.py`, `dependencies.py`: App config and DI helpers

Run
```bash
python apps/fastapi_backend/main.py --reload
```

Primary endpoints
- Core
  - GET `/` dashboard HTML
  - GET `/api` API index
  - GET `/health` overall health
- Video pipeline
  - POST `/upload` upload a video, create topics, and start AI pipeline
  - GET `/status/{task_id}` task status
  - GET `/result/{task_id}` download/redirect to output
- Streams
  - GET `/streams` list active RTSP streams
  - POST `/streams/{task_id}/stop` stop a stream
  - GET `/streams/{task_id}/status` stream status (includes `rtsp://localhost:8554/outstream_{task_id}`)
- AI Orchestration
  - POST `/api/ai/pipeline/start` start all services for a task
  - POST `/api/ai/pipeline/{task_id}/stop` stop all services
  - GET `/api/ai/pipeline/{task_id}/status` pipeline status
  - GET `/api/ai/health` aggregated health
  - GET `/api/ai/yolox/services` list YOLOX tasks
  - GET `/api/ai/yolox/{task_id}/status` YOLOX status
- Annotation helpers
  - GET `/api/annotation/{task_id}/rtsp_url` processed RTSP URL
  - GET `/api/annotation/{task_id}/videos` list rendered videos
  - GET `/api/annotation/{task_id}/download/{filename}` download a video
  - GET `/api/annotation/{task_id}/status` combined status
- WebSocket (MongoDB results)
  - `ws://localhost:8000/ws/pose/{task_id}` live/simulated playback

Dependencies
- Kafka broker at `localhost:9092`
- Optional MongoDB if using annotation MongoDB output
- RTSP base `rtsp://localhost:8554`

Typical flow
1) Start YOLOX, RTMPose, ByteTrack, Annotation services (or let `/upload` start them)
2) POST `/upload` with a video file → creates topics → starts pipeline
3) Watch processed RTSP at `rtsp://localhost:8554/outstream_{task_id}` or download results


