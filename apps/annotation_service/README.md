### Annotation Service (Visualization & Aggregation)

Purpose
- Subscribe multi-inputs:
  - Raw frames: `raw_frames_{task_id}`
  - Poses: `rtmpose_results_{task_id}`
  - Tracking: `bytetrack_tracking_{task_id}`
- Draw bboxes, skeletons, and trajectories
- Output:
  - RTSP stream: `rtsp://localhost:8554/outstream_{task_id}`
  - Optional MongoDB records
  - Optional MP4 files in `output_videos/{task_id}`

Key files
- `main.py`: Starts the FastAPI management API (default port 8004)
- `service.py`: Service definition using contanos BaseAIService
- `annotation_worker.py`: Frame fusion + drawing using `FrameAnnotator` and `TrajectoryDrawer`
- `frame_annotator.py`: Simple drawing of boxes and skeletons
- `service_manager.py`: Service metadata (ports, topics)
- `api.py`: Optional custom router

Kafka topics (per task)
- Inputs: `raw_frames_{task_id}`, `rtmpose_results_{task_id}`, `bytetrack_tracking_{task_id}`
- Outputs: RTSP `outstream_{task_id}` (via RTSPOutput), optional MongoDB, optional MP4 files
- Consumer groups: `annotation_raw_{task_id}`, `annotation_pose_{task_id}`, `annotation_track_{task_id}`

Default port
- Management API: 8004

Config
- See `apps/dev_pose_estimation_config.yaml` → `annotation`
  - `input` (multi Kafka inputs)
  - `outputs`: list of outputs (e.g., `rtsp`, `mongodb`)
  - `video_output`: file output options
  - `debug_output_dir`

Run
1) Start management API
```bash
python apps/annotation_service/main.py
```

2) Start a task instance via REST
```bash
curl -X POST 'http://localhost:8004/services/start' \
  -H 'Content-Type: application/json' \
  -d '{
        "task_id": "camera1",
        "config_path": "apps/dev_pose_estimation_config.yaml"
      }'
```

3) CLI (direct service)
```bash
python apps/annotation_service/service.py --task-id camera1 --config apps/dev_pose_estimation_config.yaml
```

Viewing results
- RTSP: `rtsp://localhost:8554/outstream_{task_id}` (use VLC/FFplay)
- Files: `apps/fastapi_backend/outputs/output_videos/{task_id}` (via backend helper)
- WebSocket (backend): `ws://localhost:8000/ws/pose/{task_id}` streams MongoDB results

Management API (common endpoints)
- Same as YOLOX: `/`, `/services/*`, `/health`

Message formats (input → output)
- Inputs: `image_bytes`, `pose_estimations`, `tracked_poses`
- Output to Kafka/RTSP: rendered frames are streamed; MongoDB documents contain `task_id`, `frame_id`, `tracked_poses_results`

Notes
- Kafka default: `localhost:9092`
- RTSP default base: `rtsp://localhost:8554`
- Ensure MongoDB is reachable if `mongodb` output is enabled


