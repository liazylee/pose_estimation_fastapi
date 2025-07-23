# Background Tasks for Video Processing
# This module contains the core video processing pipeline logic

"""
Background tasks for video processing pipeline.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

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

    try:
        # Update status to processing
        if task_id in status_db:
            status_db[task_id].status = "processing"
            status_db[task_id].progress = 10
            status_db[task_id].updated_at = datetime.now(timezone.utc)

        # Extract and publish frames
        # Extract and publish video segments to Kafka
        logger.info(f"🎞 Extracting & publishing from {video_path}")
        await extract_and_publish_async(
            video_path=video_path,
            task_id=task_id,
            segment_time=2.0,
            bootstrap_servers=kafka_controller.bootstrap_servers
        )

        # Update progress
        if task_id in status_db:
            status_db[task_id].progress = 50
            status_db[task_id].updated_at = datetime.now(timezone.utc)

        # Wait for AI services to process
        # In production, this would monitor the bytetrack topic for completion

        # TODO: Implement proper completion detection
        # For now, we'll simulate with a timeout
        logger.info("📡 Waiting for AI services to complete processing...")
        await wait_for_completion(task_id, timeout_seconds=120, status_db=status_db)

        # Generate output file path
        # output_path = Path(f"/tmp/video_outputs/{task_id}_output.mp4")
        # output_path.parent.mkdir(exist_ok=True)

        # Update final status
        if task_id in status_db:
            status_db[task_id].status = "completed"
            status_db[task_id].progress = 100
            status_db[task_id].updated_at = datetime.now(timezone.utc)

        logger.info(f"✅ Task {task_id} completed successfully.")

        # Schedule topic cleanup
        kafka_controller.delete_topics_for_task(task_id, delay_seconds=2 * 60 * 60)


    except Exception as e:

        logger.error(f"❌ Error processing task {task_id}: {e}")

        if task_id in status_db:
            status_db[task_id].status = "failed"

            status_db[task_id].error = str(e)

            status_db[task_id].updated_at = datetime.now(timezone.utc)

        kafka_controller.delete_topics_for_task(task_id, delay_seconds=10 * 60)


async def wait_for_completion(task_id: str,
                              timeout_seconds: int = 300,
                              status_db: Dict[str, TaskStatus] = None):
    """
    Async wait for downstream services to process the video (simulated).
    In real system: monitor Kafka topic progress or completion flag.
    """
    start_time = asyncio.get_event_loop().time()
    check_interval = 5

    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        elapsed = asyncio.get_event_loop().time() - start_time
        progress = min(50 + (elapsed / timeout_seconds) * 40, 90)

        if status_db and task_id in status_db:
            status_db[task_id].progress = int(progress)
            status_db[task_id].updated_at = datetime.now(timezone.utc)

        await asyncio.sleep(check_interval)

    logger.info(f"⌛️ Completion wait finished for task {task_id}")
