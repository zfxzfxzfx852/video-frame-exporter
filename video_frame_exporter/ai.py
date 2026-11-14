"""ONNX 模型推理：MiDaS 单目深度、U2NetP 分割；GPU 自动探测 + 懒加载单例。"""
import os
from functools import lru_cache

import cv2
import numpy as np
import onnxruntime as ort

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)


def available_providers():
    """返回当前 onnxruntime 可用的执行提供者，优先 GPU。"""
    avail = set(ort.get_available_providers())
    providers = []
    for gpu in ("CUDAExecutionProvider", "CoreMLExecutionProvider",
                "DmlExecutionProvider", "TensorrtExecutionProvider"):
        if gpu in avail:
            providers.append(gpu)
    providers.append("CPUExecutionProvider")
    return providers


_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class _BaseModel:
    def __init__(self, model_path):
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"模型不存在: {model_path}，先运行 scripts/download_models.py")
        self.sess = ort.InferenceSession(
            model_path, providers=available_providers())
        self.in_name = self.sess.get_inputs()[0].name
        self.providers = self.sess.get_providers()

    def _normalize(self, img_bgr, size):
        x = cv2.resize(img_bgr, (size, size))
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - _MEAN) / _STD
        return x.transpose(2, 0, 1)[None]


class DepthEstimator(_BaseModel):
    """MiDaS v2.1 small，输出 0-255 相对深度，值越大越近。"""

    def infer(self, img_bgr, invert=False):
        h, w = img_bgr.shape[:2]
        x = self._normalize(img_bgr, 256)
        depth = self.sess.run(None, {self.in_name: x})[0][0]
        depth = (depth - depth.min()) / max(depth.max() - depth.min(), 1e-6)
        out = (depth * 255).astype(np.uint8)
        if invert:
            out = 255 - out
        return cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)


class Segmenter(_BaseModel):
    """U2NetP，输出 0-255 主体概率蒙版，255 为主体。"""

    def infer(self, img_bgr):
        h, w = img_bgr.shape[:2]
        x = self._normalize(img_bgr, 320)
        pred = self.sess.run(None, {self.in_name: x})[-1][0, 0]
        pred = np.clip(pred, 0.0, 1.0) * 255.0
        return cv2.resize(pred.astype(np.uint8), (w, h),
                          interpolation=cv2.INTER_CUBIC)


@lru_cache(maxsize=2)
def get_depth_estimator(model_path=None):
    return DepthEstimator(model_path or os.path.join(MODEL_DIR, "midas_small.onnx"))


@lru_cache(maxsize=2)
def get_segmenter(model_path=None):
    return Segmenter(model_path or os.path.join(MODEL_DIR, "u2netp.onnx"))
