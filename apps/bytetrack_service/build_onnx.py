import torch
from torchreid import models

# 1) 不关心分类数量，只要特征
model = models.build_model(
    name='osnet_x0_25',
    num_classes=0,  # 🔹 不建分类层
    pretrained=False
)

# 2) 加载权重（丢掉分类器的参数）
state = torch.load("osnet_x0_25_msmt17.pt", map_location='cpu')
state = {k: v for k, v in state.items() if not k.startswith('classifier')}
model.load_state_dict(state, strict=False)

model.eval()

# 3) dummy 输入
dummy = torch.randn(1, 3, 256, 128)

# 4) 导出 ONNX（输出 embedding）
torch.onnx.export(
    model, dummy, "osnet_x0_25_msmt17.onnx",
    input_names=["images"], output_names=["embeddings"],
    opset_version=12,
    dynamic_axes={"images": {0: "batch"}, "embeddings": {0: "batch"}}
)

print("✅ 导出完成: osnet_x0_25_msmt17.onnx")
