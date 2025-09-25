"""Prometheus metrics for the FastAPI backend service."""

from __future__ import annotations

from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

from contanos.metrics.prometheus import LABEL_NAMES, MetricsLabelContext


BACKEND_SERVICE_NAME = "fastapi_backend"


def _create_context(worker_id: str, topic: str, task_id: Optional[str] = None) -> MetricsLabelContext:
    """Create a metrics label context scoped to this backend service."""

    return MetricsLabelContext(
        service=BACKEND_SERVICE_NAME,
        worker_id=worker_id,
        topic=topic,
        initial_task_id=task_id,
    )


def create_task_context(task_id: Optional[str]) -> MetricsLabelContext:
    """Return a metrics context for task orchestration stages."""

    return _create_context(worker_id="task_manager", topic="backend_tasks", task_id=task_id)


def create_wait_context(task_id: Optional[str]) -> MetricsLabelContext:
    """Return a metrics context for simulated task completion waiting."""

    return _create_context(worker_id="task_waiter", topic="backend_wait", task_id=task_id)


def create_video_publish_context(topic: str, task_id: Optional[str]) -> MetricsLabelContext:
    """Return a metrics context for publishing video segments to Kafka."""

    return _create_context(worker_id="video_ingest", topic=topic, task_id=task_id)


# Video ingestion metrics ---------------------------------------------------

backend_segment_extraction_seconds = Histogram(
    "backend_segment_extraction_seconds",
    "Time spent extracting video segments with FFmpeg before publishing to Kafka.",
    LABEL_NAMES,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0),
)

backend_segment_publish_seconds = Histogram(
    "backend_segment_publish_seconds",
    "Time spent awaiting Kafka acknowledgement for published video segments.",
    LABEL_NAMES,
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

backend_segments_sent_total = Counter(
    "backend_segments_sent_total",
    "Total number of video segments successfully published to Kafka by the backend.",
    LABEL_NAMES,
)

backend_segment_bytes_sent_total = Counter(
    "backend_segment_bytes_sent_total",
    "Total bytes of encoded video segments sent to Kafka by the backend.",
    LABEL_NAMES,
)

backend_segment_failures_total = Counter(
    "backend_segment_failures_total",
    "Total number of failures encountered during segment extraction or publishing.",
    LABEL_NAMES,
)


# Task orchestration metrics ------------------------------------------------

backend_active_tasks = Gauge(
    "backend_active_tasks",
    "Number of video processing tasks currently managed by the backend.",
    LABEL_NAMES,
)

backend_task_progress_percent = Gauge(
    "backend_task_progress_percent",
    "Latest reported progress percentage for backend managed tasks.",
    LABEL_NAMES,
)

backend_task_total_duration_seconds = Histogram(
    "backend_task_total_duration_seconds",
    "Total runtime of backend managed video processing tasks.",
    LABEL_NAMES,
    buckets=(5, 10, 30, 60, 120, 300, 600, 900, 1800),
)

backend_task_upload_seconds = Histogram(
    "backend_task_upload_seconds",
    "Time spent in the upload stage before backend processing begins.",
    LABEL_NAMES,
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

backend_task_publish_seconds = Histogram(
    "backend_task_publish_seconds",
    "Time spent publishing video segments to Kafka for a task.",
    LABEL_NAMES,
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

backend_task_wait_seconds = Histogram(
    "backend_task_wait_seconds",
    "Time spent waiting for downstream AI services to finish a task.",
    LABEL_NAMES,
    buckets=(5, 10, 30, 60, 120, 300, 600, 900),
)

backend_completion_timeouts_total = Counter(
    "backend_completion_timeouts_total",
    "Total number of simulated completion waits that expired before downstream confirmation.",
    LABEL_NAMES,
)

backend_completion_failures_total = Counter(
    "backend_completion_failures_total",
    "Total number of simulated completion waits that failed due to unexpected errors.",
    LABEL_NAMES,
)
