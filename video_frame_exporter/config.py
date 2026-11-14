"""配置：数据类 + JSON/YAML 文件加载 + 参数预设。"""
from dataclasses import dataclass, asdict, field
from typing import Optional
import json
import os


PRESETS = {
    "anime": {
        "canny_low": 40, "canny_high": 120, "min_component": 50,
        "line_width": 2, "keyframe_threshold": 20, "color_levels": 6,
    },
    "realistic": {
        "canny_low": 60, "canny_high": 180, "min_component": 30,
        "line_width": 1, "keyframe_threshold": 16, "color_levels": 8,
    },
    "sketch_only": {
        "depth": False, "segment": False, "cutout": False,
        "base_color": False, "palette": False, "prores": False,
    },
    "fast": {
        "depth": False, "segment": False, "cutout": False,
        "gif": False, "prores": False, "keyframe_threshold": 25,
    },
}


@dataclass
class ExportConfig:
    fps: float = 24.0
    lineart_bg: str = "transparent"          # transparent / white / both
    canny_low: int = 50
    canny_high: int = 150
    line_width: int = 1
    min_component: int = 30
    keyframe_threshold: int = 18
    mask_threshold: int = 127
    color_levels: int = 6
    palette_k: int = 8
    depth_invert: bool = False
    trial: bool = False                       # True=只处理前 10 帧用于参数试跑
    workers: int = 1                          # 1=串行，>1 启用多进程帧池
    # 功能开关
    keyframes: bool = True
    stabilize: bool = True
    contact_sheet: bool = True
    palette: bool = True
    base_color: bool = True
    depth: bool = True
    segment: bool = True
    cutout: bool = True
    gif: bool = True
    prores: bool = True
    zip_output: bool = True

    @classmethod
    def from_file(cls, path: str) -> "ExportConfig":
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        if path.endswith(".json"):
            data = json.loads(text)
        else:
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("读取 YAML 配置需要安装 pyyaml") from exc
            data = yaml.safe_load(text)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_preset(cls, name: str, overrides: Optional[dict] = None) -> "ExportConfig":
        if name not in PRESETS:
            raise ValueError(f"未知预设: {name}，可选 {list(PRESETS)}")
        data = dict(PRESETS[name])
        if overrides:
            data.update({k: v for k, v in overrides.items()
                         if k in cls.__dataclass_fields__})
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)
