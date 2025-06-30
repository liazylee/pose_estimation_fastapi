Perfect — here is 04_fastapi_pipeline_controller.md, which defines how your FastAPI backend coordinates the entire video
processing pipeline: from accepting uploads, spawning AI tasks, producing Kafka messages, and managing output streams.

This doc is focused on how engineers should structure and implement the API layer.

⸻

📘 04_fastapi_pipeline_controller.md

🚀 FastAPI Pipeline Controller Specification

⸻

🧭 Purpose

The FastAPI server is the control hub of the system. It manages:
• Uploads from users
• Unique task creation
• Kafka topic creation
• Frame production
• Task lifecycle (status, cleanup)
• Exposure of final output (RTSP stream or downloadable MP4)

⸻

🔗 API Endpoints

✅ /upload — Upload a Video File

POST /upload

Request
• multipart/form-data
• file: uploaded .mp4 video

Response

{
"task_id": "abc123",
"message": "Task started successfully.",
"stream_url": "rtsp://yourdomain/abc123"
}

⸻

✅ /status/{task_id} — Check Task Status

GET /status/abc123

Response

{
"task_id": "abc123",
"status": "running", // or "completed", "failed"
"progress": "85%"
}

⸻

✅ /result/{task_id} — Get Output Video

GET /result/abc123

Response
• Redirects to MP4 file if stored
• Or returns 404 if not completed

⸻

🧱 Core Functional Workflow

1. User Uploads File
   • FastAPI saves video to /tmp or a job directory
   • Generates a unique task_id = uuid4()

2. Create Kafka Topics
   • raw_frames_{task_id}
   • yolox_{task_id}
   • rtmpose_{task_id}
   • bytetrack_{task_id}

Set retention.ms for safety (e.g., 10 min)

3. Start Background Pipeline

FastAPI launches:
• Frame producer (ffmpeg or cv2.VideoCapture)
• Kafka producer: pushes JPEGs to raw_frames_{task_id}

4. AI Services Process the Frames
   • Already running services subscribe dynamically based on topic name pattern

5. Annotation Service Completes the Output
   • Publishes annotated stream to:
   • RTSP stream (using FFmpeg/GStreamer server)
   • Optional: saves MP4

6. Schedule Topic Cleanup
   • After task ends, wait ~60 seconds and delete topics via Kafka Admin API

⸻

⚙️ Core Code Structure (FastAPI)

main.py (Simplified)

from fastapi import FastAPI, UploadFile, BackgroundTasks
import uuid
import shutil
from app.kafka_utils import create_kafka_topics, delete_kafka_topics
from app.tasks import process_video_task

app = FastAPI()

@app.post("/upload")
async def upload(file: UploadFile, background_tasks: BackgroundTasks):
task_id = str(uuid.uuid4())
file_path = f"/tmp/{task_id}.mp4"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    create_kafka_topics(task_id)
    background_tasks.add_task(process_video_task, task_id, file_path)
    
    return {
        "task_id": task_id,
        "message": "Task started successfully.",
        "stream_url": f"rtsp://yourdomain:8554/{task_id}"
    }

⸻

🔧 process_video_task(task_id, file_path)

def process_video_task(task_id: str, video_path: str):
from app.kafka_utils import delete_kafka_topics
from app.video_utils import extract_frames_and_publish
from time import sleep

    extract_frames_and_publish(video_path, task_id)
    
    sleep(60)  # Allow AI services to finalize
    delete_kafka_topics(task_id)

⸻

🛡️ Error Handling
• Catch Kafka broker errors (e.g., topic creation)
• Validate video file formats
• Timeout video processing if no frames are published within a threshold

⸻

🧪 Testing Plan
• Unit test: upload endpoint with sample video
• Mock Kafka in unit tests or use local broker
• Integration test: end-to-end pipeline (video → AI → RTSP/MP4)

⸻

📦 Directory Structure Example

```text
project_root/
├── apps/
│   ├── fastapi_backend/           # FastAPI control server
│   │   ├── main.py
│   │   ├── tasks.py
│   │   ├── kafka_controller.py
│   │   ├── video_utils.py
│   │   └── configs/
│   │       └── default.yaml
│   │
│   ├── yolox_service/             # YOLOX detection service
│   │   ├── main.py
│   │   ├── service.py             # Kafka I/O logic
│   │   └── config.yaml
│   │
│   ├── rtmpose_service/
│   │   ├── main.py
│   │   ├── service.py
│   │   └── config.yaml
│   │
│   ├── bytetrack_service/
│   │   ├── main.py
│   │   ├── service.py
│   │   └── config.yaml
│   │
│   └── annotation_service/
│       ├── main.py
│       ├── render.py
│       └── rtsp_output.py

├── core/
│   ├── models/
│   │   ├── base_model.py          # Abstract AIModel class
│   │   ├── yolox_model.py         # Implements base_model
│   │   ├── rtmpose_model.py
│   │   ├── bytetrack_model.py
│   └── utils/
│       ├── kafka_io.py            # Kafka I/O helpers
│       ├── serializers.py         # Frame encode/decode
│       └── config_loader.py       # YAML loader, schema validator

├── docker/
│   ├── yolox.Dockerfile
│   ├── rtmpose.Dockerfile
│   ├── backend.Dockerfile
│   └── compose.yaml

├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/

├── scripts/
│   └── start_local_pipeline.sh

└── README.md
```

⸻

✅ Summary

Component Role
FastAPI /upload Accepts video, launches pipeline
Kafka topic manager Creates and deletes dynamic topics
Background task Runs video → frame + Kafka publishing
Stream endpoint Returns RTSP or MP4 result

⸻
