📘 01_system_architecture.md

🧩 System Architecture: Multi-User AI Video Analysis Platform

⸻

🧭 Overview

This system processes uploaded videos through an AI-powered pose estimation pipeline (YOLOX → RTMPose → ByteTrack →
Annotation) using FastAPI for control, Kafka for communication, and modular AI services for inference.

The architecture supports multi-user, concurrent video uploads, each dynamically assigned its own Kafka pipeline.

⸻

🏗️ Component Diagram

```mermaid
+----------------+      +------------------+      +-----------------+
|  User Uploads  | ---> | FastAPI Backend  | ---> | Kafka Topic     |
|   Video File   |      | (/upload route)  |      | Management      |
+----------------+      +------------------+      +-----------------+
                                                        |
                                                        ▼
                                              ┌────────────────────┐
                                              │  raw_frames_<task> │◄──┐
                                              └────────────────────┘   │
                                                        │              │
                        +-------------------------------┘              │
                        ▼                                              │
                +----------------+                                     │
                |  YOLOX Service | ──────────────► yolox_<task>        │
                +----------------+                                     │
                        ▼                                              │
                +----------------+                                     │
                | RTMPose Service| ─────────────► rtmpose_<task>       │
                +----------------+                                     │
                        ▼                                              │
                +----------------+                                     │
                | ByteTrack Svc  | ─────────────► bytetrack_<task>     │
                +----------------+                                     │
                        ▼                                              │
                +----------------+                                     │
                | Annotation Svc |                                     │
                +----------------+                                     │
                        ▼
        RTSP Stream or MP4 File Output
        

```

🧠 Component Responsibilities

🔹 1. FastAPI Backend  
• Accepts video uploads from users  
• Generates a unique task_id  
• Creates task-specific Kafka topics  
• Launches frame producer in background  
• Triggers deletion of topics upon task completion

⸻

🔹 2. Kafka Broker  
• Handles inter-service communication  
• Stores messages for:  
• raw_frames_<task_id>:   raw JPEG-compressed images  
• yolox_<task_id>: bounding boxes  
• rtmpose_<task_id>: keypoints  
• bytetrack_<task_id>: tracked poses with IDs  
• Allows service decoupling and parallel processing

⸻

🔹 3. Frame Producer (Video Source)  
• Reads uploaded MP4 or RTSP video  
• Splits into frames  
• Compresses to JPEG  
• Publishes each frame to raw_frames_<task_id>

⸻

🔹 4. YOLOX Service  
• Subscribes to raw_frames_<task_id>  
• Detects human bounding boxes  
• Publishes results to yolox_<task_id>

⸻

🔹 5. RTMPose Service  
• Subscribes to yolox_<task_id>  
• Estimates pose keypoints per detected box  
• Publishes to rtmpose_<task_id>

⸻

🔹 6. ByteTrack Service  
• Subscribes to rtmpose_<task_id>  
• Assigns persistent track_id to each person    
• Publishes to bytetrack_<task_id>

⸻

🔹 7. Annotation Service  
• Subscribes to:  
• raw_frames_<task_id> (for image)  
• bytetrack_<task_id> (for overlay data  
• Draws keypoints, IDs, and annotations  
• Outputs video via RTSP or writes to MP4  
• Signals task completion

⸻

🧼 Kafka Topic Lifecycle  
• Topics are created dynamically per task  
• Named using: raw_frames_<task_id>, etc.  
• Deleted via Kafka Admin API 60 seconds after task completion  
• Default retention.ms set (10 min) as a fail-safe

⸻

🔐 Considerations  
• Each AI service is isolated and subscribes only to task-specific topics  
• Services can be run in parallel across tasks for multi-user support  
• All data is ephemeral unless the output video is explicitly stored  
• Topics must be cleaned up to prevent broker bloat  
