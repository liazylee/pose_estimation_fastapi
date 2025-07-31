from contanos.ai_service import create_ai_service_app, run_ai_service_app
from service_manager import ByteTrack_CONFIG, get_service_manager

#
app = create_ai_service_app(ByteTrack_CONFIG, get_service_manager)

if __name__ == "__main__":
    run_ai_service_app(app, ByteTrack_CONFIG)
