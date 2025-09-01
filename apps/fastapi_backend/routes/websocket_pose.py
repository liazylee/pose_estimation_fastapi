"""
WebSocket API for real-time pose annotation results from MongoDB.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import parse_qs

import motor.motor_asyncio
import yaml
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter()

CONFIG_PATH = Path(__file__).resolve().parents[2] / "dev_pose_estimation_config.yaml"


# Load MongoDB configuration from config file
def load_mongodb_config() -> Dict[str, str]:
    """Load MongoDB configuration from dev_pose_estimation_config.yaml"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Extract MongoDB config from annotation output
        for output in config.get("annotation", {}).get("outputs", []):
            if output.get("type") == "mongodb":
                return {
                    "mongo_uri": output["mongo_uri"],
                    "database": output["database"],
                    "collection": output["collection"]
                }

        raise ValueError("MongoDB configuration not found in annotation outputs")
    except Exception as e:
        logger.error(f"Failed to load MongoDB config: {e}")
        raise


class ConnectionManager:
    """Manages WebSocket connections for pose results."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        """Accept a WebSocket connection for a specific task."""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)
        logger.info(f"WebSocket connected for task_id: {task_id}")

    def disconnect(self, websocket: WebSocket, task_id: str):
        """Remove a WebSocket connection."""
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        logger.info(f"WebSocket disconnected for task_id: {task_id}")

    async def send_data(self, data: Dict[str, Any], task_id: str):
        """Send data to all connections for a specific task."""
        if task_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_text(json.dumps(data))
                except Exception as e:
                    logger.error(f"Error sending data to WebSocket: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                self.disconnect(conn, task_id)


manager = ConnectionManager()


class PoseDataStreamer:
    """Streams pose annotation data from MongoDB."""

    def __init__(self):
        self.mongo_config = load_mongodb_config()
        self.client = None
        self.collection = None

    async def connect_to_mongodb(self):
        """Connect to MongoDB."""
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_config["mongo_uri"])
            db = self.client[self.mongo_config["database"]]
            self.collection = db[self.mongo_config["collection"]]
            # Test connection
            await self.client.admin.command('ping')
            logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def disconnect_from_mongodb(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    async def stream_pose_data(self, task_id: str, simulate_realtime: bool = False, fps: float = 25.0):
        """Stream pose data for a specific task_id."""
        if self.collection is None:
            await self.connect_to_mongodb()

        if simulate_realtime:
            await self._simulate_realtime_playback(task_id, fps)
        else:
            await self._stream_live_data(task_id)

    async def _simulate_realtime_playback(self, task_id: str, fps: float):
        """Simulate real-time playback by sending all frames in order with timing."""
        try:
            # Fetch all pose data for this task_id, sorted by frame_id
            query = {"task_id": task_id}
            cursor = self.collection.find(query).sort("frame_id", 1)
            all_frames = await cursor.to_list(length=None)

            if not all_frames:
                logger.warning(f"No pose data found for task_id: {task_id}")
                return

            logger.info(f"Starting simulated playback of {len(all_frames)} frames for task_id: {task_id} at {fps} FPS")

            # Calculate delay between frames based on FPS
            frame_delay = 1.0 / fps

            # Send frames in order with timing
            for frame_data in all_frames:
                # Check if connection still exists
                if task_id not in manager.active_connections:
                    logger.info(f"No active connections for task_id: {task_id}, stopping playback")
                    break

                # Convert ObjectId to string for JSON serialization
                if "_id" in frame_data:
                    frame_data["_id"] = str(frame_data["_id"])

                # Add playback metadata
                frame_data["playback_mode"] = "simulation"
                frame_data["fps"] = fps

                await manager.send_data(frame_data, task_id)

                # Wait for next frame timing
                await asyncio.sleep(frame_delay)

            # Send completion signal
            completion_data = {
                "task_id": task_id,
                "playback_mode": "simulation",
                "status": "completed",
                "total_frames": len(all_frames)
            }
            await manager.send_data(completion_data, task_id)
            logger.info(f"Completed simulated playback for task_id: {task_id}")

        except Exception as e:
            logger.error(f"Error in simulated playback: {e}")
            error_data = {
                "task_id": task_id,
                "playback_mode": "simulation",
                "status": "error",
                "error": str(e)
            }
            await manager.send_data(error_data, task_id)

    async def _stream_live_data(self, task_id: str):
        """Stream live pose data as it becomes available."""
        last_frame_id = -1

        while task_id in manager.active_connections:
            try:
                # Query for new pose annotations with this task_id
                query = {
                    "task_id": task_id,
                    "frame_id": {"$gt": last_frame_id}
                }

                cursor = self.collection.find(query).sort("frame_id", 1)
                results = await cursor.to_list(length=None)

                if results:
                    # Send each result
                    for result in results:
                        # Convert ObjectId to string for JSON serialization
                        if "_id" in result:
                            result["_id"] = str(result["_id"])

                        # Add live mode metadata
                        result["playback_mode"] = "live"

                        await manager.send_data(result, task_id)
                        last_frame_id = result["frame_id"]

                    logger.info(f"Sent {len(results)} pose results for task_id: {task_id}")

                # Wait before next query
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Error streaming pose data: {e}")
                await asyncio.sleep(5.0)  # Wait longer on error


streamer = PoseDataStreamer()


@router.websocket("/ws/pose/{task_id}")
async def websocket_pose_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint to stream pose annotation results for a specific task_id.
    
    Args:
        task_id: The task identifier to stream results for
    
    Query Parameters:
        simulate: Set to 'true' to enable simulation mode for real-time playback
        fps: Frames per second for simulation mode (default: 30.0)
    
    Usage:
        Live mode: ws://localhost:8000/ws/pose/{task_id}
        Simulation mode: ws://localhost:8000/ws/pose/{task_id}?simulate=true&fps=25
    """
    # Parse query parameters from WebSocket URL
    query_params = parse_qs(str(websocket.url.query))

    # Check if simulation mode is requested
    simulate_realtime = query_params.get('simulate', ['true'])[0].lower() == 'true'
    fps = float(query_params.get('fps', ['25.0'])[0])

    # Validate FPS range
    if fps <= 0 or fps > 120:
        fps = 30.0
        logger.warning(f"Invalid FPS value, using default: {fps}")

    logger.info(f"WebSocket connection for task_id: {task_id}, simulate: {simulate_realtime}, fps: {fps}")

    await manager.connect(websocket, task_id)

    # Start streaming data in background with appropriate mode
    stream_task = asyncio.create_task(streamer.stream_pose_data(task_id, simulate_realtime, fps))

    try:
        while True:
            # Keep connection alive and handle any incoming messages
            try:
                data = await websocket.receive_text()
                logger.info(f"Received message from client: {data}")

                # Handle client control messages
                try:
                    message = json.loads(data)
                    if message.get("action") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON message from client: {data}")

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task_id: {task_id}")
    finally:
        manager.disconnect(websocket, task_id)
        stream_task.cancel()

        try:
            await stream_task
        except asyncio.CancelledError:
            pass


@router.get("/api/pose/{task_id}/latest",
            description="""
             使用方式
  // 实时模式（原有功能）
  ws://localhost:8000/ws/pose/{task_id}

  // 模拟播放模式，30 FPS
  ws://localhost:8000/ws/pose/{task_id}?simulate=true

  // 模拟播放模式，自定义25 FPS  
  ws://localhost:8000/ws/pose/{task_id}?simulate=true&fps=25
""", )
async def get_latest_pose_results(task_id: str, limit: int = Query(10, ge=1, le=100)):
    """
    HTTP endpoint to get the latest pose results for a task_id.
    
    Args:
        task_id: The task identifier
        limit: Maximum number of results to return (1-100)
    """
    try:
        if streamer.collection is None:
            await streamer.connect_to_mongodb()

        # Query for the latest results
        query = {"task_id": task_id}
        cursor = streamer.collection.find(query).sort("frame_id", -1).limit(limit)
        results = await cursor.to_list(length=limit)

        # Convert ObjectId to string for JSON serialization
        for result in results:
            if "_id" in result:
                result["_id"] = str(result["_id"])

        return {
            "task_id": task_id,
            "count": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error fetching pose results: {e}")
        return {"error": str(e)}, 500
