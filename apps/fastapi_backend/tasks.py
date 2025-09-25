# Background Tasks for Video Processing
# This module contains the core video processing pipeline logic

"""
Background tasks for video processing pipeline.
"""
import asyncio
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Dict, Optional

from apps.fastapi_backend.metrics import (
    backend_active_tasks,
    backend_completion_failures_total,
    backend_completion_timeouts_total,
    backend_task_progress_percent,
    backend_task_publish_seconds,
    backend_task_total_duration_seconds,
    backend_task_upload_seconds,
    backend_task_wait_seconds,
    create_task_context,
    create_wait_context,
)
from contanos.metrics.prometheus import MetricsLabelContext
from kafka_controller import KafkaController
from schemas import TaskStatus
from video_utils import extract_and_publish_async

logger = logging.getLogger(__name__)


async def process_video_task(task_id: str,
                             video_path: str,
                             kafka_controller: KafkaController,
                             status_db: Dict[str, TaskStatus]):
    """
    Async background task to process uploaded video and stream it to Kafka.
    """
    logger.info(f"🚀 Starting video processing for task {task_id}")

    metrics_context = create_task_context(task_id)
    labels = metrics_context.labels_for(task_id)
    backend_active_tasks.labels(**labels).inc()
    total_start = perf_counter()

    try:
        now = datetime.now(timezone.utc)
        if task_id in status_db:
            task_status = status_db[task_id]
            if task_status.created_at:
                upload_duration = (now - task_status.created_at).total_seconds()
                if upload_duration >= 0:
                    backend_task_upload_seconds.labels(**labels).observe(upload_duration)
            backend_task_progress_percent.labels(**labels).set(task_status.progress)
            task_status.status = "processing"
            task_status.progress = 10
            task_status.updated_at = now
            backend_task_progress_percent.labels(**labels).set(task_status.progress)
        else:
            backend_task_progress_percent.labels(**labels).set(0)

        # Update status to processing
        logger.info(f"🎞 Extracting & publishing from {video_path}")
        publish_start = perf_counter()
        await extract_and_publish_async(
            video_path=video_path,
            task_id=task_id,
            segment_time=2.0,
            bootstrap_servers=kafka_controller.bootstrap_servers
        )
        publish_duration = perf_counter() - publish_start
        backend_task_publish_seconds.labels(**labels).observe(publish_duration)

        # Update progress
        if task_id in status_db:
            status_db[task_id].progress = 50
            status_db[task_id].updated_at = datetime.now(timezone.utc)
            backend_task_progress_percent.labels(**labels).set(status_db[task_id].progress)

        # Wait for AI services to process
        # In production, this would monitor the bytetrack topic for completion

        # TODO: Implement proper completion detection
        # For now, we'll simulate with a timeout
        logger.info("📡 Waiting for AI services to complete processing...")
        wait_context = create_wait_context(task_id)
        wait_start = perf_counter()
        await wait_for_completion(
            task_id,
            timeout_seconds=120,
            status_db=status_db,
            metrics_context=wait_context,
            progress_labels=labels,
        )
        wait_duration = perf_counter() - wait_start
        backend_task_wait_seconds.labels(**labels).observe(wait_duration)

        # Generate output file path
        # output_path = Path(f"/tmp/video_outputs/{task_id}_output.mp4")
        # output_path.parent.mkdir(exist_ok=True)

        # Update final status
        if task_id in status_db:
            status_db[task_id].status = "completed"
            status_db[task_id].progress = 100
            status_db[task_id].updated_at = datetime.now(timezone.utc)
            backend_task_progress_percent.labels(**labels).set(status_db[task_id].progress)

        logger.info(f"✅ Task {task_id} completed successfully.")

        # Schedule topic cleanup
        kafka_controller.delete_topics_for_task(task_id, delay_seconds=2 * 60 * 60)


    except Exception as e:

        logger.error(f"❌ Error processing task {task_id}: {e}")

        if task_id in status_db:
            status_db[task_id].status = "failed"

            status_db[task_id].error = str(e)

            status_db[task_id].updated_at = datetime.now(timezone.utc)
            backend_task_progress_percent.labels(**labels).set(status_db[task_id].progress)

        kafka_controller.delete_topics_for_task(task_id, delay_seconds=10 * 60)

    finally:
        total_duration = perf_counter() - total_start
        backend_task_total_duration_seconds.labels(**labels).observe(total_duration)
        backend_active_tasks.labels(**labels).dec()
        backend_task_progress_percent.labels(**labels).set(0)


async def wait_for_completion(
    task_id: str,
    timeout_seconds: int = 300,
    status_db: Optional[Dict[str, TaskStatus]] = None,
    *,
    metrics_context: Optional[MetricsLabelContext] = None,
    progress_labels: Optional[Dict[str, str]] = None,
) -> None:
    """
    Async wait for downstream services to process the video (simulated).
    In real system: monitor Kafka topic progress or completion flag.
    """
    loop = asyncio.get_event_loop()
    start_time = loop.time()
    check_interval = 5

    labels = None
    if metrics_context is not None:
        labels = metrics_context.labels_for(task_id)
        if progress_labels is None:
            progress_labels = labels

    timed_out = True

    try:
        while loop.time() - start_time < timeout_seconds:
            elapsed = loop.time() - start_time
            progress = min(50 + (elapsed / timeout_seconds) * 40, 90)

            if status_db and task_id in status_db:
                status_db[task_id].progress = int(progress)
                status_db[task_id].updated_at = datetime.now(timezone.utc)

            if progress_labels is not None:
                backend_task_progress_percent.labels(**progress_labels).set(int(progress))

            await asyncio.sleep(check_interval)

    except Exception:
        timed_out = False
        if labels is not None:
            backend_completion_failures_total.labels(**labels).inc()
        raise

    else:
        if timed_out:
            if status_db and task_id in status_db:
                status_db[task_id].progress = 90
                status_db[task_id].updated_at = datetime.now(timezone.utc)

            if progress_labels is not None:
                backend_task_progress_percent.labels(**progress_labels).set(90)

            if labels is not None:
                backend_completion_timeouts_total.labels(**labels).inc()

        logger.info(f"⌛️ Completion wait finished for task {task_id}")
