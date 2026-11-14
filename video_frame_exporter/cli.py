"""命令行入口，参数与旧版 scripts/extract_frames.py 完全兼容。"""
import argparse
import json
import os

from .config import ExportConfig
from .pipeline import batch_process


def build_parser():
    ap = argparse.ArgumentParser(description="视频帧序列全功能导出")
    ap.add_argument("--input", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", help="JSON/YAML 配置文件路径")
    ap.add_argument("--preset", help="参数预设：anime / realistic / sketch_only / fast")
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--lineart-bg", choices=["transparent", "white", "both"],
                    default="transparent")
    ap.add_argument("--canny-low", type=int, default=50)
    ap.add_argument("--canny-high", type=int, default=150)
    ap.add_argument("--line-width", type=int, default=1)
    ap.add_argument("--min-component", type=int, default=30)
    ap.add_argument("--keyframe-threshold", type=int, default=18)
    ap.add_argument("--mask-threshold", type=int, default=127)
    ap.add_argument("--color-levels", type=int, default=6)
    ap.add_argument("--palette-k", type=int, default=8)
    ap.add_argument("--workers", type=int, default=1, help="多进程帧池工作数")
    ap.add_argument("--depth-invert", action="store_true")
    for flag, text in [
        ("keyframes", "关键帧提取"), ("stabilize", "线稿时域稳定"),
        ("contact-sheet", "接触表"), ("palette", "主色卡"),
        ("base-color", "自动底色"), ("depth", "深度图"),
        ("segment", "主体蒙版"), ("cutout", "透明抠图"),
        ("gif", "GIF 预览"), ("prores", "ProRes MOV"),
        ("zip", "打包 zip")]:
        ap.add_argument("--no-" + flag, dest=flag.replace("-", "_") if flag != "zip"
                        else "zip_output",
                        action="store_false", help="关闭" + text)
    ap.set_defaults(keyframes=True, stabilize=True, contact_sheet=True,
                    palette=True, base_color=True, depth=True, segment=True,
                    cutout=True, gif=True, prores=True, zip_output=True)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.config:
        cfg = ExportConfig.from_file(args.config)
    elif args.preset:
        cfg = ExportConfig.from_preset(args.preset)
    else:
        cfg = ExportConfig()
    # 命令行显式参数覆盖配置/预设
    defaults = build_parser().parse_args(
        ["--input", args.input[0], "--output", args.output])
    for k, v in vars(args).items():
        if k in ExportConfig.__dataclass_fields__ and v != getattr(defaults, k):
            setattr(cfg, k, v)
    result = batch_process(args.input, args.output, cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
