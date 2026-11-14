"""向后兼容模块：模型实现已迁移至 video_frame_exporter.ai。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from video_frame_exporter.ai import (  # noqa: F401
    DepthEstimator, Segmenter, available_providers,
    get_depth_estimator, get_segmenter,
)
