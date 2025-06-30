📘 05_kafka_lifecycle_manager.md

🧠 Kafka Lifecycle Management

⸻

🧭 Purpose

Each video processing task uses its own isolated set of Kafka topics (e.g., raw_frames_<task_id>, etc.). To ensure Kafka
remains performant and does not accumulate unused topics, this module handles:
• Dynamic topic creation on task start
• Safe retention configuration
• Delayed deletion of topics after task completion

⸻

🔗 When Lifecycle Actions Happen

Lifecycle Stage Action
Task Created Create all needed topics
Task Running Kafka services read/write data
Task Completed Wait (e.g., 60s), then delete topics

⸻

🏗️ Topic Naming Convention

All topics are namespaced by task_id:
• raw_frames_<task_id>
• yolox_<task_id>
• rtmpose_<task_id>
• bytetrack_<task_id>

Optionally prefix with ai. or task. if you want further namespacing.

⸻

🧱 Topic Configuration (on Create)

Recommended Configs:

Key Value Description
retention.ms 600000 Auto-expire messages after 10 min
segment.bytes 104857600 Split logs by 100 MB for fast delete
cleanup.policy delete Standard Kafka cleanup strategy

These settings ensure unused topics don’t linger in storage or memory.

⸻

🧰 Example Code: Create Topics (Python)

Using kafka-python:

from kafka.admin import KafkaAdminClient, NewTopic

def create_kafka_topics(task_id: str, bootstrap_servers: str = "localhost:9092"):
admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)

    topic_configs = {
        "retention.ms": "600000",  # 10 min
        "segment.bytes": "104857600"
    }

    topic_names = [f"{prefix}_{task_id}" for prefix in ["raw_frames", "yolox", "rtmpose", "bytetrack"]]

    topics = [
        NewTopic(name=name, num_partitions=1, replication_factor=1, topic_configs=topic_configs)
        for name in topic_names
    ]

    admin.create_topics(new_topics=topics, validate_only=False)

⸻

🧹 Example Code: Delete Topics

def delete_kafka_topics(task_id: str, delay_seconds: int = 60, bootstrap_servers: str = "localhost:9092"):
import time
time.sleep(delay_seconds)

    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)

    topic_names = [f"{prefix}_{task_id}" for prefix in ["raw_frames", "yolox", "rtmpose", "bytetrack"]]
    admin.delete_topics(topics=topic_names)

✅ delete.topic.enable=true must be set in Kafka server config for this to work.

⸻

🔄 Auto Cleanup Alternative

If you prefer not to delete topics manually:
• Rely solely on retention.ms (messages expire)
• Periodically run a Kafka admin script to clean up expired but unused topics

This works if your cluster tolerates higher topic counts but prefers automated operations.

⸻

🔐 Safety Recommendations

Tip Why
Monitor topic count with Prometheus Prevent topic explosion
Validate task_id pattern Avoid malicious topic injection
Use partition=1 for all topics Keep system simple unless scaling AI services
Add retry logic for topic creation Broker may take time to acknowledge

⸻

✅ Summary

Operation Tool When Called
Create topics KafkaAdminClient.create_topics()    On upload/task start
Set retention On creation Always
Delete topics KafkaAdminClient.delete_topics()    After task ends + delay

⸻
