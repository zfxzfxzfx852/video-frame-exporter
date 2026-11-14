"""处理管线：抽帧、逐帧推理（串行/多进程）、线稿后处理、预览产物与清单。"""
import datetime
import json
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Optional

import cv2
import numpy as np

from . import vfx
from .config import ExportConfig
from .logging_utils import get_logger

logger = get_logger()

DIR_NAMES = ("color", "lineart", "lineart_white", "edge_raw", "keyframes",
             "depth", "mask", "cutout", "basecolor", "preview",
             "video", "prores")


def _run(cmd):
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


# ---------- 多进程 worker ----------

_WORKER_ENGINES = {}


def _init_worker(cfg_dict: dict):
    _WORKER_ENGINES["cfg"] = cfg_dict
    from . import ai
    _WORKER_ENGINES["ai"] = ai


def _cutout(bgr, hard_mask):
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[..., 3] = hard_mask
    return rgba


def _process_frame(args):
    frame_path, name, out_dir, cfg_dict = args
    from . import ai
    a = cfg_dict
    bgr = cv2.imread(frame_path)

    ep = os.path.join(out_dir, "edge_raw", name)
    if not os.path.isfile(ep):
        cv2.imwrite(ep, vfx.raw_edges(bgr, a["canny_low"], a["canny_high"]))

    if a["depth"]:
        dp = os.path.join(out_dir, "depth", name)
        if not os.path.isfile(dp):
            eng = ai.get_depth_estimator()
            cv2.imwrite(dp, eng.infer(bgr, a["depth_invert"]))

    if a["segment"] or a["cutout"]:
        mp = os.path.join(out_dir, "mask", name)
        if not os.path.isfile(mp):
            eng = ai.get_segmenter()
            soft = eng.infer(bgr)
            hard = np.where(soft >= a["mask_threshold"], 255, 0).astype(np.uint8)
            cv2.imwrite(mp, hard)
        else:
            hard = cv2.imread(mp, cv2.IMREAD_GRAYSCALE)
        if a["cutout"]:
            cp = os.path.join(out_dir, "cutout", name)
            if not os.path.isfile(cp):
                cv2.imwrite(cp, _cutout(bgr, hard))

    if a["base_color"]:
        bp = os.path.join(out_dir, "basecolor", name)
        if not os.path.isfile(bp):
            edges = cv2.imread(ep, cv2.IMREAD_GRAYSCALE)
            cv2.imwrite(bp, vfx.base_color(bgr, edges, a["color_levels"]))

    return name, vfx.phash(bgr)


def process_video(video: str, out: str, config: Optional[ExportConfig] = None,
                  progress_cb: Optional[Callable[[int, int, str], None]] = None) -> dict:
    """处理单个视频，返回统计信息。progress_cb(done, total, phase)。"""
    a = config or ExportConfig()
    cfg = a.to_dict()
    os.makedirs(out, exist_ok=True)
    width, height, src_fps, duration = probe(video)
    video = os.path.abspath(video)
    dirs = {k: os.path.join(out, k) for k in DIR_NAMES}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    # 1. 抽彩色帧
    expected = max(1, round(a.fps * duration))
    have = len([f for f in os.listdir(dirs["color"]) if f.endswith(".png")])
    if have < expected:
        logger.info("抽帧 fps=%s -> %s", a.fps, dirs["color"])
        _run(["ffmpeg", "-y", "-i", video, "-vf", f"fps={a.fps}",
              os.path.join(dirs["color"], "frame_%06d.png")])
    names = sorted(f for f in os.listdir(dirs["color"]) if f.endswith(".png"))
    total = len(names)

    # 2. 逐帧处理（串行 / 多进程）
    tasks = [(os.path.join(dirs["color"], n), n, out, cfg) for n in names]
    hashes = {}
    if a.workers and a.workers > 1:
        workers = min(a.workers, os.cpu_count() or 1)
        logger.info("多进程帧池 workers=%s", workers)
        with ProcessPoolExecutor(max_workers=workers,
                                 initializer=_init_worker,
                                 initargs=(cfg,)) as pool:
            futures = [pool.submit(_process_frame, t) for t in tasks]
            done = 0
            for fut in as_completed(futures):
                n, h = fut.result()
                hashes[n] = h
                done += 1
                if progress_cb:
                    progress_cb(done, total, "帧处理")
    else:
        for i, t in enumerate(tasks, start=1):
            n, h = _process_frame(t)
            hashes[n] = h
            if progress_cb:
                progress_cb(i, total, "帧处理")

    # 3. 关键帧
    hash_list = [hashes[n] for n in names]
    key_idx = vfx.select_keyframes(hash_list, a.keyframe_threshold) if a.keyframes else [0]
    key_names = [names[i] for i in key_idx]

    # 4. 线稿后处理
    raws = [cv2.imread(os.path.join(dirs["edge_raw"], n), cv2.IMREAD_GRAYSCALE)
            for n in names]
    for i, name in enumerate(names):
        window = raws[max(0, i - 1): i + 2] if a.stabilize else [raws[i]]
        edge = vfx.vote_edges(window) if len(window) > 1 else raws[i]
        edge = vfx.thicken_edges(vfx.clean_edges(edge, a.min_component), a.line_width)
        if a.lineart_bg in ("transparent", "both"):
            cv2.imwrite(os.path.join(dirs["lineart"], name), vfx.edges_to_alpha(edge))
        if a.lineart_bg in ("white", "both"):
            cv2.imwrite(os.path.join(dirs["lineart_white"], name),
                        vfx.edges_to_white(edge))
        if name in key_names:
            shutil.copy2(os.path.join(dirs["color"], name),
                         os.path.join(dirs["keyframes"], name))
            la = os.path.join(dirs["lineart"], name)
            if os.path.isfile(la):
                shutil.copy2(la, os.path.join(dirs["keyframes"], "line_" + name))
    shutil.rmtree(dirs["edge_raw"], ignore_errors=True)

    with open(os.path.join(out, "keyframes_index.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(key_names))

    # 5. 接触表
    if a.contact_sheet:
        step = max(1, total // 40)
        sample = [os.path.join(dirs["color"], n) for n in names[::step]]
        vfx.build_contact_sheet(sample).save(
            os.path.join(dirs["preview"], "contact_all.jpg"))
        if len(key_names) > 1:
            vfx.build_contact_sheet(
                [os.path.join(dirs["color"], n) for n in key_names]).save(
                os.path.join(dirs["preview"], "contact_keyframes.jpg"))

    # 6. 色卡
    if a.palette:
        mid = cv2.imread(os.path.join(dirs["color"], names[total // 2]))
        vfx.palette_image(vfx.kmeans_palette(mid, a.palette_k)).save(
            os.path.join(dirs["preview"], "palette.jpg"))

    # 7. 原视频 / GIF / ProRes
    shutil.copy2(video, os.path.join(dirs["video"], os.path.basename(video)))
    if a.gif:
        gp = os.path.join(dirs["preview"], "preview.gif")
        if not os.path.isfile(gp):
            _run(["ffmpeg", "-y", "-i", video, "-vf",
                  "fps=%d,scale=360:-1:flags=lanczos,split[s0][s1];"
                  "[s0]palettegen[p];[s1][p]paletteuse" % a.fps, gp])
    if a.prores:
        pp = os.path.join(dirs["prores"],
                          os.path.splitext(os.path.basename(video))[0] + ".mov")
        if not os.path.isfile(pp):
            _run(["ffmpeg", "-y", "-i", video, "-c:v", "prores_ks",
                  "-profile:v", "2", "-pix_fmt", "yuv422p10le",
                  "-c:a", "pcm_s16le", pp])

    # 8. manifest
    with open(os.path.join(out, "manifest.txt"), "w", encoding="utf-8") as f:
        f.write(f"""视频帧序列导出清单
生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
源视频：{os.path.basename(video)}
分辨率：{width}x{height}
源帧率：{src_fps:.3f} fps｜抽帧帧率：{a.fps:g} fps
视频时长：{duration:.3f} 秒｜总帧数：{total}｜关键帧数：{len(key_names)}
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

    result = {"frames": total, "keyframes": len(key_names), "width": width,
              "height": height, "duration": round(duration, 3)}
    logger.info("完成: %s", result)
    return result


def batch_process(videos, out: str, config: Optional[ExportConfig] = None,
                  progress_cb=None) -> dict:
    a = config or ExportConfig()
    results = {}
    if len(videos) == 1:
        stem = os.path.splitext(os.path.basename(videos[0]))[0]
        results[stem] = process_video(videos[0], os.path.abspath(out), a, progress_cb)
    else:
        for v in videos:
            stem = os.path.splitext(os.path.basename(v))[0]
            results[stem] = process_video(
                v, os.path.join(os.path.abspath(out), stem), a, progress_cb)
    zip_path = ""
    if a.zip_output:
        root = os.path.abspath(out)
        zip_path = shutil.make_archive(root, "zip", root_dir=root)
    return {"projects": results, "zip": zip_path}
