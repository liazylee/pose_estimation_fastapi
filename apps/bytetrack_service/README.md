### ByteTrack Service (Multi-Object Tracking)

Purpose
- Subscribe detections from `yolox_detections_{task_id}`
- Run ByteTrack to assign stable IDs across frames
- Publish tracking to `bytetrack_tracking_{task_id}`

Key files
- `main.py`: Starts the FastAPI management API (default port 8003)
- `service.py`: Service definition using contanos BaseAIService
- `bytetrack_worker.py`: Tracking logic using `ByteTracker`
- `bytetracker.py`: Minimal ByteTrack implementation (IoU + greedy assignment)
- `service_manager.py`: Service metadata (ports, topics)
- `api.py`: Optional custom router

Kafka topics (per task)
- Input: `yolox_detections_{task_id}`
- Output: `bytetrack_tracking_{task_id}`
- Consumer group: `bytetrack_consumers_{task_id}`

Default port
- Management API: 8003

Config
- See `apps/dev_pose_estimation_config.yaml` → `bytetrack`
  - `track_thresh`, `match_thresh`, `track_buffer`, `frame_rate`, `per_class`

Run
1) Start management API
```bash
python apps/bytetrack_service/main.py
```

2) Start a task instance via REST
```bash
curl -X POST 'http://localhost:8003/services/start' \
  -H 'Content-Type: application/json' \
  -d '{
        "task_id": "camera1",
        "config_path": "apps/dev_pose_estimation_config.yaml"
      }'
```

3) CLI (direct service)
```bash
python apps/bytetrack_service/service.py --task-id camera1 --config apps/dev_pose_estimation_config.yaml
```

Management API (common endpoints)
- Same as YOLOX: `/`, `/services/*`, `/health`

Message formats
- Input detections:
```json
{
  "detections": [ { "bbox": [x1,y1,x2,y2], "confidence": 0.9 } ],
  "frame_id": <int>,
  "task_id": "camera1"
}
```
- Output tracking:
```json
{
  "tracked_poses": [ { "track_id": <int>, "bbox": [x1,y1,x2,y2], "score": <float> } ],
  "frame_id": <int>,
  "task_id": "camera1"
}
```

Notes
- Default device in config is `cpu` for tracking


