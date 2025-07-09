from rtmlib.tools.pose_estimation import RTMPose  # noqa: E402

device = "cuda"
model_input_size = (640, 640)
onnx_model = "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/yolox_m_8xb8-300e_humanart-c2c7a14a.zip"
backend = "onnxruntime"

rtmpose = RTMPose(
    model_input_size=model_input_size,
    onnx_model=onnx_model,
    device=device,
    backend=backend
)
