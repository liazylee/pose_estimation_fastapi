from contanos.ai_service import create_ai_service_app, run_ai_service_app
from service_manager import get_service_manager, RTMPOSE_CONFIG

# 创建FastAPI应用
app = create_ai_service_app(RTMPOSE_CONFIG, get_service_manager)

if __name__ == "__main__":
    run_ai_service_app(app, RTMPOSE_CONFIG) 