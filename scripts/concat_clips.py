#!/usr/bin/env python3
"""把多段视频按顺序拼接为一个视频（重编码，兼容不同片段参数）。"""
import argparse
import json
import subprocess
import sys


def has_audio(path):
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", "-of", "json", path,
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False
    return bool(json.loads(r.stdout).get("streams"))


def main():
    ap = argparse.ArgumentParser(description="多段视频顺序拼接")
    ap.add_argument("clips", nargs="+", help="按顺序传入的视频片段")
    ap.add_argument("--output", required=True, help="输出视频路径")
    args = ap.parse_args()

    for p in args.clips:
        if not __import__("os").path.isfile(p):
            sys.exit("片段不存在: " + p)

    n = len(args.clips)
    with_audio = all(has_audio(p) for p in args.clips)

    cmd = ["ffmpeg", "-y"]
    for p in args.clips:
        cmd += ["-i", p]

    if with_audio:
        labels = "".join(f"[{i}:v][{i}:a]" for i in range(n))
        cmd += [
            "-filter_complex",
            f"{labels}concat=n={n}:v=1:a=1[outv][outa]",
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        ]
    else:
        labels = "".join(f"[{i}:v]" for i in range(n))
        cmd += [
            "-filter_complex",
            f"{labels}concat=n={n}:v=1:a=0[outv]",
            "-map", "[outv]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ]
    cmd.append(args.output)

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("拼接失败:\n" + r.stderr[-2000:])
    print(json.dumps({"output": args.output, "clips": n,
                      "audio": with_audio}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
