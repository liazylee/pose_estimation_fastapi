### RTMPose Service (Pose Estimation)

Purpose
- Subscribe raw frames `raw_frames_{task_id}` and tracking results `bytetrack_tracking_{task_id}`
- Run RTMPose on per-person bboxes to estimate keypoints
- Publish results to `rtmpose_results_{task_id}`

Key files
- `main.py`: Starts the FastAPI management API (default port 8002)
- `service.py`: Service definition using contanos BaseAIService
- `rtmpose_worker.py`: Pose estimation with `rtmlib.tools.pose_estimation.RTMPose`
- `service_manager.py`: Service metadata (ports, topics)
- `api.py`: Optional custom router (default uses common router)

Kafka topics (per task)
- Inputs: `raw_frames_{task_id}`, `bytetrack_tracking_{task_id}`
- Output: `rtmpose_results_{task_id}`
- Consumer groups: `rtmpose_raw_{task_id}`, `rtmpose_det_{task_id}`

Default port
- Management API: 8002

Config
- See `apps/dev_pose_estimation_config.yaml` → `rtmpose` and `kafka`
  - `onnx_model`, `model_input_size`, `backend`
  - Input topics use `{task_id}` substitution

Run
1) Start management API
```bash
python apps/rtmpose_service/main.py
```

2) Start a task instance via REST
```bash
curl -X POST 'http://localhost:8002/services/start' \
  -H 'Content-Type: application/json' \
  -d '{
        "task_id": "camera1",
        "config_path": "apps/dev_pose_estimation_config.yaml"
      }'
```

3) CLI (direct service)
```bash
python apps/rtmpose_service/service.py --task-id camera1 --config apps/dev_pose_estimation_config.yaml
```

Management API (common endpoints)
- Same as YOLOX: `/`, `/services/*`, `/health`

Message formats
- Input:
  - `image_bytes` (serialized frame)
  - `tracked_poses`: list of objects `{ track_id, bbox, score }`
- Output:
```json
{
  "pose_estimations": [[ [x,y], ... ], ... ],
  "tracked_poses_results": [ { "track_id": <int>, "bbox": [...], "score": <float>, "pose": [[x,y], ...] }, ... ],
  "frame_id": <int>,
  "task_id": "camera1"
}
```

Notes
- Kafka default: `localhost:9092`
- Backend default: `onnxruntime` (configurable)


