import asyncio
import logging
import math

from aiokafka import AIOKafkaProducer

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


async def get_duration_and_fps(video_path: str):
    """Get video duration and FPS using async ffprobe."""
    # Get duration
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

    # Get FPS
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

    return duration, fps


async def extract_and_publish_async(video_path: str,
                                    task_id: str,
                                    segment_time: float = 2.0,
                                    bootstrap_servers: str = 'localhost:9092'):
    """Async version: stream video segments to Kafka with preserved codec."""

    duration, fps = await get_duration_and_fps(video_path)
    segment_count = math.ceil(duration / segment_time)

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks='all',
        max_request_size=10 * 1024 * 1024,  # 10 MB

    )
    await producer.start()

    topic = f"raw_frames_{task_id}"

    try:
        for segment_idx in range(segment_count):
            start_time = segment_idx * segment_time
            global_frame_idx = int(start_time * fps)

            ffmpeg_proc = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-ss', str(start_time),
                '-i', video_path,
                '-t', str(segment_time),
                '-c', 'copy',
                '-f', 'mp4',
                '-movflags', 'frag_keyframe+empty_moov',
                'pipe:1',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )

            stdout, _ = await ffmpeg_proc.communicate()

            if not stdout:
                logger.warning(f"Failed to extract video segment {segment_idx}")
                continue

            kafka_key = f"{global_frame_idx}".encode()
            await producer.send_and_wait(topic, key=kafka_key, value=stdout, )
            logger.info(f"Extracted video segment {segment_idx}")

    finally:
        await producer.stop()
        logger.info(f"Extracted video segment {segment_count}")
