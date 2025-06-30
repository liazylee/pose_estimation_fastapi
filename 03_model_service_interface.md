Here is the complete content for 03_model_service_interface.md — the AI Model Service Interface specification —
formatted in clean Markdown and ready for copying or saving.

⸻

📘 03_model_service_interface.md

🧠 AI Model Service Interface Specification

This document defines a standard interface for AI model services (YOLOX, RTMPose, ByteTrack). The goal is to ensure all
models can be initialized, loaded, and executed using a consistent pattern — making it easier to:
• Swap models in and out
• Test individual modules
• Standardize message formats
• Scale services independently

⸻

📐 Interface Class

class AIModel:
def __init__(self, config: dict):
"""Initialize model and load resources."""
...

    def predict(self, input_data: dict) -> dict:
        """Run inference on one input frame."""
        ...

You can optionally support:

def predict_batch(self, input_batch: List[dict]) -> List[dict]:
"""Optional: batch processing for performance."""

⸻

🧾 Input Format (Standardized)

The predict() method receives a dictionary:

input_data = {
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"image": np.ndarray, # Decoded RGB image (from JPEG)
"additional_data": dict # Optional, model-specific input (e.g. detections)
}

⸻

📤 Output Format (Standardized)

Returned as a dictionary matching Kafka schema:

{
"task_id": "abc123",
"frame_id": 42,
"timestamp": "2025-06-26T12:30:00Z",
"model": "yolox", # or "rtmpose", "bytetrack"
"result": [...]     # Model-specific result list
}

⸻

🔧 Example: YOLOXModel

class YOLOXModel(AIModel):
def __init__(self, config):
self.model = load_yolox(config["weights"])
self.threshold = config.get("confidence_threshold", 0.5)

    def predict(self, input_data):
        image = input_data["image"]
        detections = self.model.detect(image)

        filtered = [
            {
                "person_id": i,
                "bbox": det["bbox"],
                "confidence": det["conf"]
            }
            for i, det in enumerate(detections)
            if det["conf"] > self.threshold
        ]

        return {
            "task_id": input_data["task_id"],
            "frame_id": input_data["frame_id"],
            "timestamp": input_data["timestamp"],
            "model": "yolox",
            "result": filtered
        }

⸻

🔧 Example: RTMPoseModel

class RTMPoseModel(AIModel):
def __init__(self, config):
self.model = load_rtmpose(config["weights"])

    def predict(self, input_data):
        image = input_data["image"]
        bboxes = input_data["additional_data"]["detections"]

        keypoints_list = self.model.estimate(image, bboxes)

        result = []
        for i, (bbox, kpts) in enumerate(zip(bboxes, keypoints_list)):
            result.append({
                "person_id": i,
                "bbox": bbox["bbox"],
                "keypoints": kpts
            })

        return {
            "task_id": input_data["task_id"],
            "frame_id": input_data["frame_id"],
            "timestamp": input_data["timestamp"],
            "model": "rtmpose",
            "result": result
        }

⸻

🔧 Example: ByteTrackModel

```python
class ByteTrackModel(AIModel):
    def __init__(self, config):
        self.tracker = ByteTrack(config)

    def predict(self, input_data):
        poses = input_data["additional_data"]["poses"]
        tracked = self.tracker.update(poses)

        return {
            "task_id": input_data["task_id"],
            "frame_id": input_data["frame_id"],
            "timestamp": input_data["timestamp"],
            "model": "bytetrack",
            "result": [
                {
                    "track_id": p["id"],
                    "keypoints": p["keypoints"]
                } for p in tracked
            ]
        }

⸻
```

✅ Summary

Method Purpose
__init__()    Loads weights and configuration
predict()    Accepts one frame, returns result
result Matches the downstream Kafka schema

⸻

Let me know if you’d like to:
• Extend this with config validation
• Export as file or integrate with core.models.base_model library design