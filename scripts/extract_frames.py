#!/usr/bin/env python3
"""主编排：抽帧并输出彩色/线稿/关键帧/深度/蒙版/抠图/底色/预览，支持批量与断点续跑。"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import vfx_utils as vfx
from ai_models import DepthEstimator, Segmenter


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{r.stderr[-2000:]}")


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:format=duration",
         "-of", "json", path], capture_output=True, text=True)
    info = json.loads(r.stdout)
    st = info["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return (int(st["width"]), int(st["height"]),
            float(num) / float(den) if float(den) else 0.0,
            float(info["format"]["duration"]))


def cutout(bgr, hard_mask):
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[..., 3] = hard_mask
    return rgba


def process_one(video, out, a):
    os.makedirs(out, exist_ok=True)
    width, height, src_fps, duration = probe(video)
    video = os.path.abspath(video)
    dirs = {k: os.path.join(out, k) for k in
            ("color", "lineart", "lineart_white", "edge_raw", "keyframes",
             "depth", "mask", "cutout", "basecolor", "preview", "video", "prores")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    # 1. 抽彩色帧（断点：帧数已齐则跳过）
    expected = max(1, round(a.fps * duration))
    have = len([f for f in os.listdir(dirs["color"]) if f.endswith(".png")])
    if have < expected:
        run(["ffmpeg", "-y", "-i", video, "-vf", f"fps={a.fps}",
             os.path.join(dirs["color"], "frame_%06d.png")])
    names = sorted(f for f in os.listdir(dirs["color"]) if f.endswith(".png"))

    depth_eng = DepthEstimator() if a.depth else None
    seg_eng = Segmenter() if (a.segment or a.cutout) else None

    hashes, soft_masks = [], []
    for name in names:
        bgr = cv2.imread(os.path.join(dirs["color"], name))
        hashes.append(vfx.phash(bgr))

        ep = os.path.join(dirs["edge_raw"], name)
        if not os.path.isfile(ep):
            cv2.imwrite(ep, vfx.raw_edges(bgr, a.canny_low, a.canny_high))

        if a.depth:
            dp = os.path.join(dirs["depth"], name)
            if not os.path.isfile(dp):
                cv2.imwrite(dp, depth_eng.infer(bgr, a.depth_invert))

        if a.segment or a.cutout:
            mp = os.path.join(dirs["mask"], name)
            if not os.path.isfile(mp):
                soft = seg_eng.infer(bgr)
                hard = np.where(soft >= a.mask_threshold, 255, 0).astype(np.uint8)
                cv2.imwrite(mp, hard)
                soft_masks.append(soft)
            else:
                hard = cv2.imread(mp, cv2.IMREAD_GRAYSCALE)
            if a.cutout:
                cp = os.path.join(dirs["cutout"], name)
                if not os.path.isfile(cp):
                    cv2.imwrite(cp, cutout(bgr, hard))

        if a.base_color:
            bp = os.path.join(dirs["basecolor"], name)
            if not os.path.isfile(bp):
                edges = cv2.imread(ep, cv2.IMREAD_GRAYSCALE)
                cv2.imwrite(bp, vfx.base_color(bgr, edges, a.color_levels))

    # 2. 关键帧选择
    key_idx = vfx.select_keyframes(hashes, a.keyframe_threshold) if a.keyframes else [0]
    key_names = [names[i] for i in key_idx]

    # 3. 线稿：三帧时域投票 + 清理 + 加粗
    raws = [cv2.imread(os.path.join(dirs["edge_raw"], n), cv2.IMREAD_GRAYSCALE)
            for n in names]
    for i, name in enumerate(names):
        window = raws[max(0, i - 1): i + 2] if a.stabilize else [raws[i]]
        edge = vfx.vote_edges(window) if len(window) > 1 else raws[i]
        edge = vfx.thicken_edges(vfx.clean_edges(edge, a.min_component), a.line_width)
        if a.lineart_bg in ("transparent", "both"):
            cv2.imwrite(os.path.join(dirs["lineart"], name), vfx.edges_to_alpha(edge))
        if a.lineart_bg in ("white", "both"):
            cv2.imwrite(os.path.join(dirs["lineart_white"], name), vfx.edges_to_white(edge))
        if name in key_names:
            shutil.copy2(os.path.join(dirs["color"], name),
                         os.path.join(dirs["keyframes"], name))
            la = os.path.join(dirs["lineart"], name)
            if os.path.isfile(la):
                shutil.copy2(la, os.path.join(dirs["keyframes"], "line_" + name))
    shutil.rmtree(dirs["edge_raw"], ignore_errors=True)

    with open(os.path.join(out, "keyframes_index.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(key_names))

    # 4. 接触表
    if a.contact_sheet:
        step = max(1, len(names) // 40)
        sample = [os.path.join(dirs["color"], n) for n in names[::step]]
        vfx.build_contact_sheet(sample).save(
            os.path.join(dirs["preview"], "contact_all.jpg"))
        if len(key_names) > 1:
            vfx.build_contact_sheet(
                [os.path.join(dirs["color"], n) for n in key_names]).save(
                os.path.join(dirs["preview"], "contact_keyframes.jpg"))

    # 5. 色卡
    if a.palette:
        mid = cv2.imread(os.path.join(dirs["color"], names[len(names) // 2]))
        vfx.palette_image(vfx.kmeans_palette(mid, a.palette_k)).save(
            os.path.join(dirs["preview"], "palette.jpg"))

    # 6. 原视频、GIF、ProRes
    shutil.copy2(video, os.path.join(dirs["video"], os.path.basename(video)))
    if a.gif:
        gp = os.path.join(dirs["preview"], "preview.gif")
        if not os.path.isfile(gp):
            run(["ffmpeg", "-y", "-i", video, "-vf",
                 "fps=%d,scale=360:-1:flags=lanczos,split[s0][s1];"
                 "[s0]palettegen[p];[s1][p]paletteuse" % a.fps, gp])
    if a.prores:
        pp = os.path.join(dirs["prores"], os.path.splitext(os.path.basename(video))[0] + ".mov")
        if not os.path.isfile(pp):
            run(["ffmpeg", "-y", "-i", video, "-c:v", "prores_ks", "-profile:v", "2",
                 "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le", pp])

    with open(os.path.join(out, "manifest.txt"), "w", encoding="utf-8") as f:
        f.write(f"""视频帧序列导出清单
生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
源视频：{os.path.basename(video)}
分辨率：{width}x{height}
源帧率：{src_fps:.3f} fps｜抽帧帧率：{a.fps:g} fps
视频时长：{duration:.3f} 秒｜总帧数：{len(names)}｜关键帧数：{len(key_names)}
帧命名：frame_000001.png 起连续编号

目录说明：
color/ 彩色帧（PNG 无损）
lineart/ 黑白线稿（透明底黑线，正片叠底上色）
lineart_white/ 白底黑线版
keyframes/ 自动提取的关键帧（彩色帧与线稿）
depth/ 灰度深度图（白=近，黑=远，用于 C4D 位移/视差）
mask/ 主体硬蒙版（白=主体）
cutout/ 主体透明抠图
basecolor/ 自动大色块底色
preview/ 接触表、色卡、GIF
prores/ ProRes MOV
video/ 原始视频
""")
    return {"frames": len(names), "keyframes": len(key_names),
            "width": width, "height": height, "duration": round(duration, 3)}


def main():
    ap = argparse.ArgumentParser(description="视频帧序列全功能导出")
    ap.add_argument("--input", nargs="+", required=True)
    ap.add_argument("--output", required=True)
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
    ap.add_argument("--depth-invert", action="store_true")
    for flag, text in [
        ("keyframes", "关键帧提取"), ("stabilize", "线稿时域稳定"),
        ("contact-sheet", "接触表"), ("palette", "主色卡"),
        ("base-color", "自动底色"), ("depth", "深度图"),
        ("segment", "主体蒙版"), ("cutout", "透明抠图"),
        ("gif", "GIF 预览"), ("prores", "ProRes MOV"), ("zip", "打包 zip")]:
        ap.add_argument("--no-" + flag, dest=flag.replace("-", "_"),
                        action="store_false", help="关闭" + text)
    ap.set_defaults(keyframes=True, stabilize=True, contact_sheet=True, palette=True,
                    base_color=True, depth=True, segment=True, cutout=True,
                    gif=True, prores=True, zip=True)
    a = ap.parse_args()

    results = {}
    if len(a.input) == 1:
        results[os.path.splitext(os.path.basename(a.input[0]))[0]] = process_one(
            a.input[0], os.path.abspath(a.output), a)
    else:
        for v in a.input:
            stem = os.path.splitext(os.path.basename(v))[0]
            results[stem] = process_one(
                v, os.path.join(os.path.abspath(a.output), stem), a)

    zip_path = ""
    if a.zip:
        root = os.path.abspath(a.output)
        base = os.path.join(os.path.dirname(root), os.path.basename(root))
        zip_path = shutil.make_archive(base, "zip", root_dir=root)

    print(json.dumps({"projects": results, "zip": zip_path},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
