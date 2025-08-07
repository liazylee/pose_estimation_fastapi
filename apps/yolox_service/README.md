### YOLOX Service (Object Detection)

Purpose
- Subscribe raw frames from Kafka `raw_frames_{task_id}`
- Run YOLOX human detection
- Publish detections to `yolox_detections_{task_id}`

Key files
- `main.py`: Starts the FastAPI management API (default port 8001)
- `service.py`: Service definition using contanos BaseAIService
- `yolox_worker.py`: Inference logic with `rtmlib.tools.object_detection.YOLOX`
- `service_manager.py`: Service metadata (ports, topics, etc.)
- `api.py`: Optional custom API router (default uses common router)

Kafka topics (per task)
- Input: `raw_frames_{task_id}`
- Output: `yolox_detections_{task_id}`
- Consumer group: `yolox_consumers_{task_id}`

Default port
- Management API: 8001

Config
- See `apps/dev_pose_estimation_config.yaml` → `yolox` and `kafka`
  - `onnx_model`, `model_input_size`, `backend`
  - Kafka input/output config strings with `{task_id}` substitution

Run
1) Start management API
```bash
python apps/yolox_service/main.py
```

2) Start a task instance via REST
```bash
curl -X POST 'http://localhost:8001/services/start' \
  -H 'Content-Type: application/json' \
  -d '{
        "task_id": "camera1",
        "config_path": "apps/dev_pose_estimation_config.yaml"
      }'
```

3) CLI (direct service, useful for debugging)
```bash
python apps/yolox_service/service.py --task-id camera1 --config apps/dev_pose_estimation_config.yaml
```

Management API (common endpoints)
- GET `/` service info
- POST `/services/start` start a task
- POST `/services/{task_id}/stop` stop a task
- POST `/services/{task_id}/complete` mark completed
- GET `/services/{task_id}/status` task status
- GET `/services` list tasks
- DELETE `/services` stop all tasks
- GET `/health` health check

Message formats
- Input: `image_bytes` (Kafka-serialized frame)
- Output:
```json
{
  "detections": [
    { "bbox": [x1, y1, x2, y2] }
  ],
  "detection_count": <int>,
  "frame_id": <int>,
  "timestamp": <int|optional>
}
```

Notes
- Kafka default: `localhost:9092`
- Inference backend default comes from `global.backend` or `yolox.backend` (e.g., onnxruntime)


