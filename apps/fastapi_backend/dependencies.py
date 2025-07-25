"""
Dependency injection and service management.
"""
from ai_service_client import AIServiceOrchestrator
from kafka_controller import KafkaController
from video_utils import RTSPStreamManager
from config import logger

# Global service instances
_kafka_controller = None
_rtsp_manager = None
_ai_orchestrator = None

def get_kafka_controller() -> KafkaController:
    """Get Kafka controller instance."""
    global _kafka_controller
    if _kafka_controller is None:
        _kafka_controller = KafkaController()
    return _kafka_controller

def get_rtsp_manager() -> RTSPStreamManager:
    """Get RTSP stream manager instance."""
    global _rtsp_manager
    if _rtsp_manager is None:
        _rtsp_manager = RTSPStreamManager()
    return _rtsp_manager

def get_ai_orchestrator() -> AIServiceOrchestrator:
    """Get AI service orchestrator instance."""
    global _ai_orchestrator
    if _ai_orchestrator is None:
        _ai_orchestrator = AIServiceOrchestrator()
    return _ai_orchestrator

async def initialize_services():
    """Initialize all services."""
    logger.info("Initializing services...")
    
    # Initialize services
    kafka_controller = get_kafka_controller()
    rtsp_manager = get_rtsp_manager()
    ai_orchestrator = get_ai_orchestrator()
    
    # Health check for AI services
    try:
        health = await ai_orchestrator.health_check()
        logger.info(f"AI Services health check: {health}")
    except Exception as e:
        logger.warning(f"AI health check failed: {e}")

async def cleanup_services():
    """Cleanup all services."""
    logger.info("Cleaning up services...")
    
    global _kafka_controller, _rtsp_manager, _ai_orchestrator
    
    # Cleanup Kafka controller
    if _kafka_controller:
        try:
            _kafka_controller.close()
        except Exception as e:
            logger.warning(f"Kafka controller cleanup failed: {e}")
    
    # Cleanup RTSP manager
    if _rtsp_manager:
        try:
            _rtsp_manager.cleanup_all()
        except Exception as e:
            logger.warning(f"RTSP stream manager cleanup failed: {e}")
    
    # Cleanup AI orchestrator
    if _ai_orchestrator:
        try:
            await _ai_orchestrator.shutdown()
        except Exception as e:
            logger.warning(f"AI orchestrator shutdown failed: {e}")
    
    # Reset instances
    _kafka_controller = None
    _rtsp_manager = None
    _ai_orchestrator = None 