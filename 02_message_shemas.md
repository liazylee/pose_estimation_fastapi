📘 02_message_schemas.md

📦 Kafka Message Schemas

This document defines the message structure for each Kafka topic used in the AI video processing pipeline. These schemas
ensure standardized communication between components.

All messages use JSON-encoded payloads with binary data fields where applicable (e.g., image_bytes).

💡 For production systems, you may later switch to Protobuf or Avro for performance and schema versioning.

⸻

🧱 1. raw_frames_<task_id>

🔹 Producer: Frame Producer (FastAPI task)

🔹 Consumers: YOLOX Service, Annotation Service

{
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"source_id": "user_upload_001",
"image_format": "jpeg",
"image_bytes": "<base64 or raw binary>"
}

Field Type Description
task_id string Unique identifier for task
frame_id int Frame sequence number
timestamp string ISO8601 format timestamp
source_id string Optional: camera ID or filename
image_format string Typically “jpeg”
image_bytes bytes JPEG-compressed image (raw or base64)

⸻

🟠 2. yolox_<task_id>

🔹 Producer: YOLOX Service

🔹 Consumers: RTMPose Service

{
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"detections": [
{
"person_id": 0,
"bbox": [x, y, w, h],
"confidence": 0.92
},
{
"person_id": 1,
"bbox": [x, y, w, h],
"confidence": 0.87
}
]
}

Field Description
person_id Local ID for indexing within frame (optional but helpful)
bbox    [x, y, width, height]
confidence Confidence score (0.0 to 1.0)

🔄 Multiple bounding boxes per frame, one per person

⸻

🟢 3. rtmpose_<task_id>

🔹 Producer: RTMPose Service

🔹 Consumers: ByteTrack Service

{
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"poses": [
{
"person_id": 0,
"bbox": [x, y, w, h],
"keypoints": [
[x1, y1, c1], [x2, y2, c2], ..., [xN, yN, cN]
]
},
{
"person_id": 1,
"bbox": [x, y, w, h],
"keypoints": [
[x1, y1, c1], ..., [xN, yN, cN]
]
}
]
}

Field Description
keypoints List of [x, y, confidence] per joint
bbox Person’s bounding box
person_id Same local ID as in YOLOX output

⸻

🟣 4. bytetrack_<task_id>

🔹 Producer: ByteTrack Service

🔹 Consumers: Annotation Service

{
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"tracked_poses": [
{
"track_id": 301,
"keypoints": [
[x1, y1, c1], ..., [xN, yN, cN]
]
},
{
"track_id": 302,
"keypoints": [
[x1, y1, c1], ..., [xN, yN, cN]
]
}
]
}

Field Description
track_id Persistent ID across frames
keypoints Person’s skeleton (same format)

⸻

⚙️ Batch-Friendly Extension (Optional)

In the future, you can batch multiple frames in one message:

{
"batch": [
{
"frame_id": 42,
"timestamp": "...",
"detections": [...]
},
{
"frame_id": 43,
"timestamp": "...",
"detections": [...]
}
]
}

⚠️ Start with per-frame messages and optimize later if needed.

⸻

✅ Summary

Topic Content Type Multi-Person Batch Possible
raw_frames_<task>    JPEG image frames ✅ 🚫 (one frame)
yolox_<task>    Bounding boxes ✅ 🔄 (future)
rtmpose_<task>    Keypoints ✅ 🔄 (future)
bytetrack_<task>    Track IDs + poses ✅ 🔄 (future)

