"""图像处理工具：线稿、时域稳定、感知哈希、关键帧、色卡、接触表、自动底色。"""
import cv2
import numpy as np
from PIL import Image, ImageDraw


# ---------- 线稿 ----------

def raw_edges(img_bgr, low, high):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    smooth = cv2.bilateralFilter(gray, 7, 50, 50)
    return cv2.Canny(smooth, low, high)


def clean_edges(edges, min_area):
    if min_area <= 1:
        return edges
    n, labels, stats, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    keep = np.zeros_like(edges)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == i] = 255
    return keep


def thicken_edges(edges, thickness):
    if thickness <= 1:
        return edges
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness, thickness))
    return cv2.dilate(edges, k)


def edges_to_white(edges):
    return 255 - edges


def edges_to_alpha(edges):
    h, w = edges.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., 3] = edges
    return out


def vote_edges(edge_imgs):
    stack = np.stack(edge_imgs, axis=0).astype(np.float32)
    return (stack.mean(axis=0) > 127).astype(np.uint8) * 255


def to_gray(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


# ---------- 感知哈希与关键帧 ----------

def phash(img_bgr, hash_size=8, highfreq=4):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    size = hash_size * highfreq
    small = cv2.resize(gray, (size, size),
                       interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)
    roi = dct[:hash_size, :hash_size]
    med = np.median(roi[1:].flatten())
    bits = (roi > med).flatten()
    return sum(int(b) << i for i, b in enumerate(bits))


def hamming(a, b):
    return (a ^ b).bit_count()


def select_keyframes(hash_values, threshold):
    chosen = [0]
    for i in range(1, len(hash_values)):
        if hamming(hash_values[i], hash_values[chosen[-1]]) > threshold:
            chosen.append(i)
    return chosen


# ---------- 色卡 ----------

def kmeans_palette(img_bgr, k=8, sample_pixels=20000):
    z = img_bgr.reshape(-1, 3).astype(np.float32)
    if len(z) > sample_pixels:
        idx = np.random.default_rng(0).choice(
            len(z), sample_pixels, replace=False)
        z = z[idx]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        z, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(-counts)
    total = len(labels)
    return [(centers[i].astype(np.uint8), float(counts[i] / total))
            for i in order]


def palette_image(palette, swatch_h=90, swatch_w=140):
    n = len(palette)
    img = Image.new("RGB", (swatch_w * n, swatch_h + 26), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i, (bgr, ratio) in enumerate(palette):
        x = i * swatch_w
        rgb = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
        draw.rectangle([x, 0, x + swatch_w - 2, swatch_h], fill=rgb)
        draw.text((x + 6, swatch_h + 5), f"{ratio*100:.1f}%", fill=(0, 0, 0))
    return img


# ---------- 接触表 ----------

def build_contact_sheet(img_paths, cols=5, thumb=(320, 180)):
    rows = (len(img_paths) + cols - 1) // cols
    pad, label_h = 6, 22
    width = cols * thumb[0] + (cols + 1) * pad
    height = rows * (thumb[1] + label_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    for n, p in enumerate(img_paths):
        r, c = divmod(n, cols)
        x = pad + c * (thumb[0] + pad)
        y = pad + r * (thumb[1] + label_h + pad)
        im = Image.open(p).convert("RGB").resize(thumb)
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + thumb[1] + 3),
                  f"frame {n + 1:06d}", fill=(0, 0, 0))
    return sheet


# ---------- 自动底色 ----------

def base_color(img_bgr, edges, color_levels=6):
    flat = cv2.pyrMeanShiftFiltering(img_bgr, sp=12, sr=24)
    z = flat.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 1.0)
    _, labels, centers = cv2.kmeans(
        z, color_levels, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    poster = centers[labels.flatten()].reshape(img_bgr.shape).astype(np.uint8)
    poster[edges > 0] = (0, 0, 0)
    return poster
