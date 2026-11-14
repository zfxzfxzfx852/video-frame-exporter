"""向后兼容模块：算法实现已迁移至 video_frame_exporter.vfx。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from video_frame_exporter.vfx import *  # noqa: F401,F403
