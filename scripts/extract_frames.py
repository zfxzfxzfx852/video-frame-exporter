#!/usr/bin/env python3
"""向后兼容入口：功能已迁移至 video_frame_exporter 包。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from video_frame_exporter.cli import main

if __name__ == "__main__":
    main()
