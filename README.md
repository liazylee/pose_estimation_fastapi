# AI Multi-Person Pose Estimation Pipeline (FastAPI + Kafka + Docker)

This repository implements a modular, microservice-based video analytics pipeline for multi-person pose estimation. It
uses FastAPI services orchestrated over Kafka topics, with per-task isolation via dynamic topic names. The base
infrastructure (Kafka, Zookeeper, RTSP server, MongoDB) is provided via Docker Compose.

# Services

- YOLOX Service (object detection)
    - Input: `raw_frames_{task_id}` → Output: `yolox_detections_{task_id}`
- ByteTrack Service (multi-object tracking)
    - Input: `yolox_detections_{task_id}` ,`raw_frames_{task_id}`  → Output: `bytetrack_tracking_{task_id}`
- RTMPose Service (pose estimation)
    - Inputs: `raw_frames_{task_id}`, `bytetrack_tracking_{task_id}` → Output: `rtmpose_results_{task_id}`
- Annotation Service (aggregation + visualization)
    - Inputs: raw frames + pose + tracking → Outputs: RTSP `rtsp://localhost:8554/outstream_{task_id}`, optional
      MongoDB, optional MP4 files
- FastAPI Backend (orchestrator + UI)
    - Starts/stops services, manages Kafka topics, exposes dashboard and APIs

## Quick start (with Docker infrastructure)

1) Start base services via Docker (Kafka, Zookeeper, RTSP, MongoDB)

```bash
./docker/start_docker_compose.sh
# or
docker compose -f docker/compose.yaml up -d
```

Notes:

- Kafka is advertised for local access at `localhost:9092` (see compose env `KAFKA_ADVERTISED_LISTENERS`)
- Kafka auto topic creation is disabled; topics are created by the backend at upload time
- Kafka UI available at `http://localhost:8080`

2) Install Python dependencies (Python 3.10+ recommended)

```bash
pip install -r requirements.txt
```

3) Start AI service management APIs (required so the backend can orchestrate)
   Option A: start all in one command

```bash
python start_services.py all
```

Option B: start individually

```bash
python apps/yolox_service/main.py
python apps/rtmpose_service/main.py
python apps/bytetrack_service/main.py
python apps/annotation_service/main.py
```

4) Start the orchestrator backend (port 8000)

```bash
python apps/fastapi_backend/main.py --reload
```

5) Run a task using the backend

- Upload a video to create Kafka topics and start the pipeline:

```bash
curl -X POST 'http://localhost:8000/upload' \
  -F 'file=@/path/to/video.mp4'
```

The backend will:

- Create Kafka topics: `raw_frames_{task_id}`, `yolox_detections_{task_id}`, `rtmpose_results_{task_id}`,
  `bytetrack_tracking_{task_id}`
- Call each service management API to start workers for that `task_id`
- Begin processing frames and streaming annotated results via RTSP

6) View results

- RTSP: `rtsp://localhost:8554/outstream_{task_id}` (VLC/FFplay)
- Download or list files via backend endpoints (see API section)
- WebSocket (pose results from MongoDB): `ws://localhost:8000/ws/pose/{task_id}`

Config

- Central config: `apps/dev_pose_estimation_config.yaml`
    - `global`: devices, backend (onnxruntime/openvino/tensorrt), workers
    - `kafka`: broker, producer/consumer defaults, topic templates
    - `yolox`, `rtmpose`, `bytetrack`, `annotation`: per-service settings
    - `service_dependencies`: startup order

Running services individually
Each service exposes a management API for starting/stopping per-task workers.

- YOLOX (port 8001)

```bash
python apps/yolox_service/main.py
curl -X POST http://localhost:8001/services/start -H 'Content-Type: application/json' -d '{"task_id":"camera1","config_path":"apps/dev_pose_estimation_config.yaml"}'
```

- ByteTrack (port 8003)

```bash
python apps/bytetrack_service/main.py
curl -X POST http://localhost:8003/services/start -H 'Content-Type: application/json' -d '{"task_id":"camera1","config_path":"apps/dev_pose_estimation_config.yaml"}'
```

- RTMPose (port 8002)

```bash
python apps/rtmpose_service/main.py
curl -X POST http://localhost:8002/services/start -H 'Content-Type: application/json' -d '{"task_id":"camera1","config_path":"apps/dev_pose_estimation_config.yaml"}'
```

- Annotation (port 8004)

```bash
python apps/annotation_service/main.py
curl -X POST http://localhost:8004/services/start -H 'Content-Type: application/json' -d '{"task_id":"camera1","config_path":"apps/dev_pose_estimation_config.yaml"}'
```

Backend APIs (selected)

- Core/UI
    - GET `/` dashboard, GET `/api` index, GET `/health`
- Video
    - POST `/upload` start a processing task from a video file
    - GET `/status/{task_id}`, GET `/result/{task_id}`
- Streams
    - GET `/streams`, POST `/streams/{task_id}/stop`, GET `/streams/{task_id}/status`
- AI Orchestration
    - POST `/api/ai/pipeline/start`, POST `/api/ai/pipeline/{task_id}/stop`
    - GET `/api/ai/pipeline/{task_id}/status`, GET `/api/ai/health`
- Annotation helpers
    - GET `/api/annotation/{task_id}/rtsp_url`, `/api/annotation/{task_id}/videos`,
      `/api/annotation/{task_id}/download/{filename}`, `/api/annotation/{task_id}/status`

Data formats (high level)

- `image_bytes`: serialized frame (Kafka); internal helpers deserialize to ndarray
- YOLOX output: `{ detections: [{bbox:[x1,y1,x2,y2]}], frame_id, ... }`
- ByteTrack output: `{ tracked_poses: [{track_id,bbox,score}], frame_id, task_id }`
- RTMPose output: `{ pose_estimations: [[[x,y],...], ...], tracked_poses_results: [...], frame_id, task_id }`
- Annotation: renders frames; optional MongoDB documents per frame

Development

- Code style: readable, explicit names, guard clauses, minimal magic
- Tests: see `tests/` for unit/integration examples
- Common framework utilities under `contanos/`

About `contanos/`

- Internal framework used by services for consistent patterns:
    - `contanos.ai_service`: `BaseAIService`, `BaseServiceManager`, common FastAPI app/router (`create_ai_service_app`),
      `ServiceConfig`
    - `contanos.base_worker`: `BaseWorker` lifecycle (`_model_init`, `_predict`, `cleanup`)
    - `contanos.io`: Kafka input/output interfaces, RTSP output, MongoDB output, multi-input/output helpers
    - `contanos.visualizer`: drawing utilities (boxes, skeletons, trajectories)
    - `contanos.utils`: serializers, YAML config loader, logging setup
      These abstractions reduce duplication across services (YOLOX, RTMPose, ByteTrack, Annotation).

Troubleshooting

- Kafka not reachable → verify broker on `localhost:9092`
- RTSP not visible → ensure RTSP server and check `rtsp://localhost:8554/outstream_{task_id}`
- GPU/ONNX backend issues → verify `onnxruntime-gpu` and CUDA versions; set `global.backend`
- MongoDB disabled or unreachable → disable `mongodb` output in `annotation.outputs` or fix URI
- Topics not created → ensure backend is used to create topics (auto-create is disabled in Docker compose)

# License
MIT License

Copyright (c) 2025 liazylee

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


# Acknowledgement
This work has received funding as an Open Call project under the SPARTA project from the European Union's Horizon Europe programme Autonomous, scalablE, tRustworthy, intelligent European meta Operating System for the IoT edge-cloud continuum (aerOS) (grant agreement No. 101069732).

LINK: https://aeros-project.eu/

