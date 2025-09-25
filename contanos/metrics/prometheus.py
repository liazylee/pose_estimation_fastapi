"""Shared Prometheus metric definitions for contanos services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from prometheus_client import Counter, Gauge, Histogram

LABEL_NAMES = ("service", "task_id", "worker_id", "topic")
DEFAULT_TASK_ID = "unknown"


# Core processing metrics
service_frames_processed_total = Counter(
    "service_frames_processed_total",
    "Total number of frames processed by the worker stage.",
    LABEL_NAMES,
)

service_frames_errors_total = Counter(
    "service_frames_errors_total",
    "Total number of frames that failed during processing.",
    LABEL_NAMES,
)

service_frame_processing_seconds = Histogram(
    "service_frame_processing_seconds",
    "Latency in seconds for processing a single frame.",
    LABEL_NAMES,
    buckets=(
        0.001,
        0.005,
        0.01,
        0.02,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2,
        5,
        10,
    ),
)


# Queue depth gauges
service_input_queue_size = Gauge(
    "service_input_queue_size",
    "Current depth of the service input queue.",
    LABEL_NAMES,
)

service_output_queue_size = Gauge(
    "service_output_queue_size",
    "Current depth of the service output queue.",
    LABEL_NAMES,
)


# Backpressure and drop monitoring
service_frames_dropped_total = Counter(
    "service_frames_dropped_total",
    "Total number of frames dropped because of timeouts or overflow.",
    LABEL_NAMES,
)

service_backpressure_events_total = Counter(
    "service_backpressure_events_total",
    "Total number of backpressure events detected by the service.",
    LABEL_NAMES,
)

service_pending_frames = Gauge(
    "service_pending_frames",
    "Number of frames pending synchronization before inference.",
    LABEL_NAMES,
)

service_interfaces_under_pressure = Gauge(
    "service_interfaces_under_pressure",
    "Number of upstream interfaces currently under backpressure.",
    LABEL_NAMES,
)


# Worker lifecycle
service_worker_restarts_total = Counter(
    "service_worker_restarts_total",
    "Total number of worker restart attempts.",
    LABEL_NAMES,
)


# Kafka I/O specific metrics
service_messages_consumed_total = Counter(
    "service_messages_consumed_total",
    "Total number of messages consumed from Kafka topics.",
    LABEL_NAMES,
)

service_messages_produced_total = Counter(
    "service_messages_produced_total",
    "Total number of messages produced to Kafka topics.",
    LABEL_NAMES,
)

service_decode_errors_total = Counter(
    "service_decode_errors_total",
    "Total number of decode errors while consuming Kafka messages.",
    LABEL_NAMES,
)

service_send_failures_total = Counter(
    "service_send_failures_total",
    "Total number of failures when sending Kafka messages.",
    LABEL_NAMES,
)


@dataclass
class MetricsLabelContext:
    """Helper for reusing Prometheus labels with dynamic task ids."""

    service: str
    worker_id: str
    topic: str
    initial_task_id: Optional[str] = None

    def __post_init__(self) -> None:
        self._base_labels = {
            "service": self.service or "unknown",
            "worker_id": str(self.worker_id) if self.worker_id is not None else "unknown",
            "topic": self.topic or "unknown",
        }
        initial = self.initial_task_id or DEFAULT_TASK_ID
        self._label_cache: Dict[str, Dict[str, str]] = {}
        self._current_task_id = DEFAULT_TASK_ID
        self.labels_for(initial)

    def labels_for(self, task_id: Optional[str]) -> Dict[str, str]:
        """Return labels for the provided task id and cache the result."""

        normalized = str(task_id) if task_id else DEFAULT_TASK_ID
        if normalized not in self._label_cache:
            labels = {**self._base_labels, "task_id": normalized}
            self._label_cache[normalized] = labels
        self._current_task_id = normalized
        return self._label_cache[normalized]

    def with_metric(self, metric, task_id: Optional[str] = None):
        """Return a labelled child for the provided metric."""

        labels = self.labels_for(task_id or self._current_task_id)
        return metric.labels(**labels)

    @property
    def current_task_id(self) -> str:
        return self._current_task_id

    @property
    def current_labels(self) -> Dict[str, str]:
        """Return the cached labels for the current task id."""

        if self._current_task_id not in self._label_cache:
            self.labels_for(self._current_task_id)
        return self._label_cache[self._current_task_id]

