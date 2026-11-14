"""ONNX 模型推理：MiDaS 单目深度估计、U2NetP 主体分割。"""
import os

import cv2
import numpy as np
import onnxruntime as ort

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)


class DepthEstimator:
    """MiDaS v2.1 small，输出 0-255 相对深度，值越大越近。"""

    def __init__(self, model_path=None):
        path = model_path or os.path.join(MODEL_DIR, "midas_small.onnx")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"深度模型不存在: {path}，先运行 scripts/download_models.py")
        self.sess = ort.InferenceSession(
            path, providers=["CPUExecutionProvider"])
        self.in_name = self.sess.get_inputs()[0].name

    _mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    _std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def infer(self, img_bgr, invert=False):
        h, w = img_bgr.shape[:2]
        x = cv2.resize(img_bgr, (256, 256))
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - self._mean) / self._std
        x = x.transpose(2, 0, 1)[None]
        depth = self.sess.run(None, {self.in_name: x})[0][0]
        depth = (depth - depth.min()) / max(depth.max() - depth.min(), 1e-6)
        out = (depth * 255).astype(np.uint8)
        if invert:
            out = 255 - out
        return cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC)


class Segmenter:
    """U2NetP，输出 0-255 主体概率蒙版，255 为主体。"""

    _mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    _std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, model_path=None):
        path = model_path or os.path.join(MODEL_DIR, "u2netp.onnx")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"分割模型不存在: {path}，先运行 scripts/download_models.py")
        self.sess = ort.InferenceSession(
            path, providers=["CPUExecutionProvider"])
        self.in_name = self.sess.get_inputs()[0].name

    def infer(self, img_bgr):
        h, w = img_bgr.shape[:2]
        x = cv2.resize(img_bgr, (320, 320))
        x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = (x - self._mean) / self._std
        x = x.transpose(2, 0, 1)[None]
        pred = self.sess.run(None, {self.in_name: x})[-1][0, 0]
        pred = np.clip(pred, 0.0, 1.0) * 255.0
        return cv2.resize(pred.astype(np.uint8), (w, h),
                          interpolation=cv2.INTER_CUBIC)
