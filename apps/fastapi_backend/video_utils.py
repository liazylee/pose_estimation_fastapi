import asyncio
import json
import logging
import math
import time

from aiokafka import AIOKafkaProducer

from apps.fastapi_backend.metrics import (
    backend_segment_bytes_sent_total,
    backend_segment_extraction_seconds,
    backend_segment_failures_total,
    backend_segment_publish_seconds,
    backend_segments_sent_total,
    create_video_publish_context,
)

logger = logging.getLogger(__name__)


class RTSPStreamManager:
    """
    TODO: Manage RTSP streams for video processing tasks.
    """

    def __init__(self):
        pass

    def get_stream_status(self, task_id: str) -> dict[str, str]:
        """
        Get the status of an RTSP stream for a given task.

        Args:
            task_id: Unique identifier for the task

        Returns:
            bool: True if the stream is active, False otherwise
        """
        # Placeholder implementation
        # In a real implementation, this would check the actual RTSP stream status
        return {
            "task_id": task_id,
            "active": False,
            "rtsp_url": None
        }

    def get_active_streams(self) -> list[dict[str, str]]:
        """
        Get a list of active RTSP streams.

        Returns:
            List of dictionaries with stream status
        """
        # Placeholder implementation
        # In a real implementation, this would return actual active streams
        return []


async def get_video_metadata(video_path: str):
    """Get duration, fps, width, height from video using ffprobe."""
    # Duration
    proc1 = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path,
        stdout=asyncio.subprocess.PIPE
    )
    stdout1, _ = await proc1.communicate()
    duration = float(stdout1.decode().strip())

    # FPS
    proc2 = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=r_frame_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path,
        stdout=asyncio.subprocess.PIPE
    )
    stdout2, _ = await proc2.communicate()
    fps_parts = stdout2.decode().strip().split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])

    # Width and Height
    proc3 = await asyncio.create_subprocess_exec(
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path,
        stdout=asyncio.subprocess.PIPE
    )
    stdout3, _ = await proc3.communicate()

    info = json.loads(stdout3.decode())
    width = info['streams'][0]['width']
    height = info['streams'][0]['height']

    return duration, fps, width, height


async def extract_and_publish_async(
    video_path: str,
    task_id: str,
    segment_time: float = 2.0,
    bootstrap_servers: str = 'localhost:9092',
) -> None:
    """Stream encoded video segments to Kafka while recording observability metrics."""

    duration, fps, width, height = await get_video_metadata(video_path)
    segment_count = math.ceil(duration / segment_time)
    channels = 3  # assuming bgr24

    topic = f"raw_frames_{task_id}"
    metrics_context = create_video_publish_context(topic=topic, task_id=task_id)
    labels = metrics_context.labels_for(task_id)

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks='all',
        max_request_size=10 * 1024 * 1024,
    )
    await producer.start()

    try:
        for segment_idx in range(segment_count):
            start_time = segment_idx * segment_time
            # 修复帧ID计算，避免int()截断导致的精度丢失
            global_frame_idx = round(start_time * fps)  # 使用round()而不是int()

            # Extract video segment
            segment_gop = round(fps * segment_time)  # 25fps×2s=50

            extract_start = time.perf_counter()
            ffmpeg_proc = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-ss', str(start_time), '-i', video_path,
                '-t', str(segment_time),
                '-an',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-g', str(segment_gop),
                '-keyint_min', str(segment_gop),
                '-pix_fmt', 'yuv420p',
                '-f', 'mp4',
                '-movflags', 'frag_keyframe+empty_moov',
                'pipe:1',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await ffmpeg_proc.communicate()
            extract_duration = time.perf_counter() - extract_start
            backend_segment_extraction_seconds.labels(**labels).observe(extract_duration)

            if ffmpeg_proc.returncode != 0:
                backend_segment_failures_total.labels(**labels).inc()
                stderr_text = stderr.decode(errors='ignore') if stderr else ''
                logger.error(
                    f"[{task_id}] FFmpeg failed for segment {segment_idx} (frame {global_frame_idx}): "
                    f"code={ffmpeg_proc.returncode}, stderr={stderr_text.strip()}"
                )
                raise RuntimeError(
                    f"FFmpeg exited with code {ffmpeg_proc.returncode} while extracting segment {segment_idx}"
                )

            if not stdout:
                backend_segment_failures_total.labels(**labels).inc()
                logger.warning(f"[{task_id}] Segment {segment_idx} is empty, skipping...")
                continue

            # Construct metadata key (JSON string)
            kafka_key = json.dumps({
                "frame_id_start": global_frame_idx,
                "width": width,
                "height": height,
                "channels": channels,
                "fps": fps,
                "segment_idx": segment_idx,  # 添加分段索引用于调试
                "start_time": start_time,  # 添加开始时间用于调试
            }).encode()

            publish_start = time.perf_counter()
            try:
                await producer.send_and_wait(topic, key=kafka_key, value=stdout)
            except Exception:
                backend_segment_failures_total.labels(**labels).inc()
                raise

            publish_duration = time.perf_counter() - publish_start
            backend_segment_publish_seconds.labels(**labels).observe(publish_duration)
            backend_segments_sent_total.labels(**labels).inc()
            backend_segment_bytes_sent_total.labels(**labels).inc(len(stdout))
            logger.info(
                f"[{task_id}] ✅ Sent segment {segment_idx} (frame {global_frame_idx}, time {start_time:.2f}s)"
            )

    finally:
        await producer.stop()
        logger.info(f"[{task_id}] ✅ All {segment_count} segments sent.")
