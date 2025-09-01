"""
MongoDB client for storing video upload records.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import motor.motor_asyncio
    from pymongo.errors import PyMongoError
    from bson import ObjectId
    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False
    logging.warning("motor not installed. Please install it with: pip install motor")

from schemas import VideoUploadRecord


def convert_objectid(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert MongoDB ObjectId to string for JSON serialization."""
    if record and "_id" in record:
        record["_id"] = str(record["_id"])
    return record


def convert_paths_to_urls(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert file paths to accessible URLs."""
    if record:
        # Convert file_path to accessible URL
        if "file_path" in record and "filename" in record:
            record["file_url"] = f"/media/uploads/{record['filename']}"
        
        # Convert output_video_path to accessible URL
        if "output_video_path" in record:
            output_filename = Path(record["output_video_path"]).name
            record["output_video_url"] = f"/media/outputs/{output_filename}"
    
    return record


class VideoRecordMongoDB:
    """MongoDB client for video upload records."""
    
    def __init__(self, mongo_uri: str = "mongodb://admin:password@localhost:27017/pose_annotations?authSource=admin"):
        if not MOTOR_AVAILABLE:
            raise ImportError("motor package is required. Install with: pip install motor")
            
        self.mongo_uri = mongo_uri
        self.database_name = "pose_annotations"
        self.collection_name = "video_uploads"
        
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db = None
        self.collection = None
        self._initialized = False
        
    async def initialize(self) -> bool:
        """Initialize MongoDB connection."""
        try:
            logging.info(f"Connecting to MongoDB for video records at {self.mongo_uri}")
            
            # Create MongoDB client
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_uri)
            
            # Test the connection
            await self.client.admin.command('ping')
            
            # Get database and collection references
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes for better performance
            await self.collection.create_index("task_id", unique=True)
            await self.collection.create_index("created_at")
            
            self._initialized = True
            logging.info(f"Video record MongoDB initialized for {self.database_name}.{self.collection_name}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to initialize video record MongoDB: {e}")
            return False
    
    async def save_video_record(self, record: VideoUploadRecord) -> bool:
        """Save a video upload record to MongoDB."""
        if not self._initialized:
            raise RuntimeError("MongoDB client not initialized")
            
        try:
            # Convert Pydantic model to dict for MongoDB
            record_dict = record.dict()
            
            # Insert document
            result = await self.collection.insert_one(record_dict)
            
            if result.inserted_id:
                logging.info(f"Saved video record for task_id: {record.task_id}")
                return True
            else:
                logging.error(f"Failed to insert video record for task_id: {record.task_id}")
                return False
                
        except PyMongoError as e:
            logging.error(f"MongoDB error saving video record: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error saving video record: {e}")
            return False
    
    async def update_video_record(self, task_id: str, update_fields: Dict[str, Any]) -> bool:
        """Update a video upload record."""
        if not self._initialized:
            raise RuntimeError("MongoDB client not initialized")
            
        try:
            # Add updated_at timestamp
            update_fields["updated_at"] = datetime.utcnow()
            
            # Update document
            result = await self.collection.update_one(
                {"task_id": task_id},
                {"$set": update_fields}
            )
            
            if result.modified_count > 0:
                logging.info(f"Updated video record for task_id: {task_id}")
                return True
            else:
                logging.warning(f"No video record found to update for task_id: {task_id}")
                return False
                
        except PyMongoError as e:
            logging.error(f"MongoDB error updating video record: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error updating video record: {e}")
            return False
    
    async def get_video_record(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a video upload record by task_id."""
        if not self._initialized:
            raise RuntimeError("MongoDB client not initialized")
            
        try:
            record = await self.collection.find_one({"task_id": task_id})
            if record:
                record = convert_objectid(record)
                record = convert_paths_to_urls(record)
            return record
            
        except PyMongoError as e:
            logging.error(f"MongoDB error retrieving video record: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error retrieving video record: {e}")
            return None
    
    async def list_video_records(self, limit: int = 50, skip: int = 0) -> list:
        """List video upload records with pagination."""
        if not self._initialized:
            raise RuntimeError("MongoDB client not initialized")
            
        try:
            cursor = self.collection.find().sort("created_at", -1).skip(skip).limit(limit)
            records = await cursor.to_list(length=limit)
            # Convert ObjectId and paths to URLs
            converted_records = []
            for record in records:
                record = convert_objectid(record)
                record = convert_paths_to_urls(record)
                converted_records.append(record)
            return converted_records
            
        except PyMongoError as e:
            logging.error(f"MongoDB error listing video records: {e}")
            return []
        except Exception as e:
            logging.error(f"Unexpected error listing video records: {e}")
            return []
    
    async def cleanup(self):
        """Close MongoDB connection."""
        if self.client:
            try:
                self.client.close()
                logging.info("Video record MongoDB client closed")
            except Exception as e:
                logging.error(f"Error closing MongoDB client: {e}")
            finally:
                self.client = None
                self.db = None
                self.collection = None
                self._initialized = False