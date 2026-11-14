#!/usr/bin/env python3
"""下载/修复技能内置 ONNX 模型（MiDaS 深度、U2NetP 分割）。"""
import os
import subprocess
import sys

MODELS = {
    "midas_small.onnx":
        "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx",
    "u2netp.onnx":
        "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
}


def main():
    model_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
    )
    os.makedirs(model_dir, exist_ok=True)
    for name, url in MODELS.items():
        path = os.path.join(model_dir, name)
        if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
            print(f"已存在: {name}")
            continue
        print(f"下载 {name} ...")
        r = subprocess.run(["curl", "-L", "--fail", "-o", path, url])
        if r.returncode != 0:
            sys.exit(f"下载失败: {url}")
    print("模型就绪:", model_dir)


if __name__ == "__main__":
    main()
