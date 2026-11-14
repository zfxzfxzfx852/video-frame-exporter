"""核心算法单元测试。"""
import cv2
import numpy as np

from video_frame_exporter import vfx
from video_frame_exporter.config import ExportConfig


def _frame():
    img = np.full((120, 160, 3), 200, dtype=np.uint8)
    cv2.rectangle(img, (40, 30), (120, 90), (30, 60, 90), -1)
    cv2.circle(img, (80, 60), 15, (255, 0, 0), -1)
    return img


def test_raw_edges_shape():
    edges = vfx.raw_edges(_frame(), 50, 150)
    assert edges.shape == (120, 160)
    assert edges.dtype == np.uint8
    assert edges.max() == 255


def test_clean_edges_removes_small_components():
    edges = np.zeros((100, 100), np.uint8)
    cv2.circle(edges, (20, 20), 2, 255, -1)   # 小碎点
    cv2.rectangle(edges, (50, 50), (90, 90), 255, 2)  # 大块
    cleaned = vfx.clean_edges(edges, 100)
    assert cleaned[20, 20] == 0
    assert cleaned[50, 70] == 255


def test_edges_to_alpha_and_white():
    edges = np.zeros((10, 10), np.uint8)
    edges[5, 5] = 255
    alpha = vfx.edges_to_alpha(edges)
    assert alpha.shape == (10, 10, 4)
    assert alpha[5, 5, 3] == 255
    white = vfx.edges_to_white(edges)
    assert white[5, 5] == 0 and white[0, 0] == 255


def test_phash_and_keyframes():
    frame = _frame()
    h1 = vfx.phash(frame)
    h2 = vfx.phash(np.roll(frame, 5, axis=1))
    assert isinstance(h1, int)
    assert 0 <= vfx.hamming(h1, h2) <= 64
    chosen = vfx.select_keyframes([h1, h1, h2, h2], 1)
    assert chosen[0] == 0 and 2 in chosen


def test_base_color():
    frame = _frame()
    edges = vfx.raw_edges(frame, 50, 150)
    poster = vfx.base_color(frame, edges, 4)
    assert poster.shape == frame.shape
    # 边缘被压黑
    assert poster[edges > 0].max() == 0


def test_config_preset_and_fields():
    cfg = ExportConfig.from_preset("fast")
    assert cfg.depth is False and cfg.cutout is False
    assert "fps" in cfg.to_dict()
