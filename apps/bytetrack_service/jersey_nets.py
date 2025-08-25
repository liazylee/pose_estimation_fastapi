#!/usr/bin/env python3
"""
Jersey OCR Neural Network Model
Stub implementation for jersey number recognition model.
"""

import timm
import torch.nn as nn
from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large


# class JerseyNetMobileNet(nn.Module):
#     """
#     Jersey number OCR model based on MobileNet backbone.
#     This is a stub implementation that should be replaced with the actual model.
#     """
#
#     def __init__(self, pretrained: bool = True):
#         super(JerseyNetMobileNet, self).__init__()
#
#         # Use MobileNetV2 as backbone
#         self.backbone = models.mobilenet_v2(pretrained=False, width_mult=0.5)
#
#         # Remove the final classifier
#         self.features = self.backbone.features
#         self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
#
#         # Custom heads for jersey number prediction
#         feature_dim = self.backbone.last_channel  # MobileNetV2 feature dimension
#
#         # Length prediction head (0: no number, 1: single digit, 2: double digit)
#         self.length_head = nn.Sequential(
#             nn.Dropout(0.2),
#             nn.Linear(feature_dim, 128),
#             nn.ReLU(),
#             nn.Dropout(0.2),
#             nn.Linear(128, 3)  # 3 classes: no number, 1 digit, 2 digits
#         )
#
#         # First digit prediction head (0-9)
#         self.digit1_head = nn.Sequential(
#             nn.Dropout(0.2),
#             nn.Linear(feature_dim, 128),
#             nn.ReLU(),
#             nn.Dropout(0.2),
#             nn.Linear(128, 10)  # 10 classes: digits 0-9
#         )
#
#         # Second digit prediction head (0-9)
#         self.digit2_head = nn.Sequential(
#             nn.Dropout(0.2),
#             nn.Linear(feature_dim, 128),
#             nn.ReLU(),
#             nn.Dropout(0.2),
#             nn.Linear(128, 10)  # 10 classes: digits 0-9
#         )
#
#     def forward(self, x):
#         """
#         Forward pass.
#
#         Args:
#             x: Input tensor of shape (batch_size, 3, H, W)
#
#         Returns:
#             tuple: (length_logits, digit1_logits, digit2_logits)
#         """
#         # Extract features
#         features = self.features(x)
#         features = self.avgpool(features)
#         features = torch.flatten(features, 1)
#
#         # Predict length and digits
#         length_logits = self.length_head(features)
#         digit1_logits = self.digit1_head(features)
#         digit2_logits = self.digit2_head(features)
#
#         return length_logits, digit1_logits, digit2_logits
#
#     def predict(self, x):
#         """
#         Predict jersey numbers with confidence scores.
#
#         Args:
#             x: Input tensor
#
#         Returns:
#             dict: Prediction results
#         """
#         with torch.no_grad():
#             length_logits, digit1_logits, digit2_logits = self.forward(x)
#
#             # Apply softmax to get probabilities
#             length_probs = F.softmax(length_logits, dim=1)
#             digit1_probs = F.softmax(digit1_logits, dim=1)
#             digit2_probs = F.softmax(digit2_logits, dim=1)
#
#             # Get predictions
#             length_pred = torch.argmax(length_probs, dim=1)
#             digit1_pred = torch.argmax(digit1_probs, dim=1)
#             digit2_pred = torch.argmax(digit2_probs, dim=1)
#
#             return {
#                 'length_pred': length_pred,
#                 'digit1_pred': digit1_pred,
#                 'digit2_pred': digit2_pred,
#                 'length_probs': length_probs,
#                 'digit1_probs': digit1_probs,
#                 'digit2_probs': digit2_probs
#             }
#
class JerseyNetMobileNet(nn.Module):
    """Jersey OCR model with MobileNetV3-Large backbone"""

    def __init__(self,
                 pretrained: bool = True,
                 dropout: float = 0.1,
                 num_len: int = 3,  # {0=no number, 1=1 digit, 2=2 digits}
                 num_digit: int = 11  # digits 0–9 (+ blank)
                 ):
        super().__init__()
        weights = MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
        self.backbone = mobilenet_v3_large(weights=weights)
        self.backbone.classifier = nn.Identity()
        self.pool = nn.AdaptiveAvgPool2d(1)
        feat_dim = 960  # last conv channels for mobilenet_v3_large

        self.feat_bn = nn.BatchNorm1d(feat_dim)
        self.dropout = nn.Dropout(dropout)

        self.len_head = nn.Linear(feat_dim, num_len)
        self.d1_head = nn.Linear(feat_dim, num_digit)
        self.d2_head = nn.Linear(feat_dim, num_digit)

    def forward(self, x):
        feats = self.backbone.features(x)  # [B,C,h,w]
        pooled = self.pool(feats).flatten(1)  # [B,C]
        pooled = self.feat_bn(pooled)
        pooled = self.dropout(pooled)
        return self.len_head(pooled), self.d1_head(pooled), self.d2_head(pooled)


class JerseyNetConvNeXt(nn.Module):
    """Jersey OCR model with ConvNeXtV2 backbone from timm"""

    def __init__(self,
                 backbone_name: str = "convnextv2_tiny.fcmae_ft_in1k",
                 pretrained: bool = True,
                 dropout: float = 0.1,
                 num_len: int = 3,
                 num_digit: int = 11,
                 freeze_stages: int = 0):
        super().__init__()
        self.backbone = timm.create_model(
            backbone_name, pretrained=pretrained,
            num_classes=0, global_pool="avg"
        )
        feat_dim = self.backbone.num_features

        if freeze_stages > 0 and hasattr(self.backbone, "stages"):
            for i, stage in enumerate(self.backbone.stages):
                if i < freeze_stages:
                    for p in stage.parameters():
                        p.requires_grad = False

        self.feat_bn = nn.BatchNorm1d(feat_dim)
        self.dropout = nn.Dropout(dropout)

        self.len_head = nn.Linear(feat_dim, num_len)
        self.d1_head = nn.Linear(feat_dim, num_digit)
        self.d2_head = nn.Linear(feat_dim, num_digit)

    def forward(self, x):
        feats = self.backbone(x)  # [B,C]
        feats = self.feat_bn(feats)
        feats = self.dropout(feats)
        return self.len_head(feats), self.d1_head(feats), self.d2_head(feats)
