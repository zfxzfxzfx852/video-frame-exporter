# 视频帧序列导出 video-frame-exporter

一句话生成短视频，并逐帧导出全套制作素材：彩色帧、透明底黑白线稿、关键帧、MiDaS 单目深度图、U2NetP 主体蒙版与透明抠图、自动大色块底色、接触表、主色卡、GIF 预览、ProRes MOV 与清单文件。全部为连续编号 PNG 序列，可直接导入 Cinema 4D（C4D）做图片序列纹理、2.5D 位移与分层合成。

全程本地运行，无需 GPU，模型通过 ONNX Runtime 在 CPU 上推理。

---

## 功能特性

- 视频生成与分段拼接：支持 4–15 秒分段生成，自动拼接为最长约 90 秒的完整视频
- 彩色帧序列：ffmpeg 按目标帧率抽帧，PNG 无损、连续编号
- 黑白线稿：双边滤波 + Canny 边缘，三帧时域投票抑制闪烁，连通域清理与线宽可调，输出透明底 / 白底两个版本
- 关键帧提取：基于感知哈希（pHash）贪心选择，减少上色工作量
- 单目深度图：MiDaS 模型输出相对深度，用于 C4D 位移与 2.5D 视差
- 主体蒙版与抠图：U2NetP 输出软/硬蒙版，一步生成带透明通道的 BGRA 抠图
- 自动底色：均值漂移 + KMeans 量化大色块，线稿边缘自动压黑
- 预览产物：接触表、主色卡、GIF、ProRes 10bit MOV
- 断点续跑：中断后重跑同一命令，已完成产物自动跳过
- 批量处理：一次传入多个视频，输出独立子目录

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- ffmpeg、ffprobe（需在 PATH 中）
- 支持 Windows / macOS / Linux

### 2. 下载安装

```bash
git clone https://github.com/zfxzfxzfx852/video-frame-exporter.git
cd video-frame-exporter
pip install -r requirements.txt
```

### 3. 下载模型权重

模型文件未纳入 Git 仓库（合计约 68MB），首次使用前执行：

```bash
python3 scripts/download_models.py
```

会自动下载并校验：

| 模型 | 用途 | 大小 |
|---|---|---|
| MiDaS v2.1 small | 单目深度估计 | 约 64MB |
| U2NetP | 主体分割 | 约 4.4MB |

### 4. 导出帧序列

```bash
python3 scripts/extract_frames.py --input source.mp4 --output my_project
```

默认全部功能开启，结束后自动打包 zip。

多视频批量处理：

```bash
python3 scripts/extract_frames.py --input a.mp4 b.mp4 c.mp4 --output batch_dir
```

多段视频拼接：

```bash
python3 scripts/concat_clips.py clip1.mp4 clip2.mp4 clip3.mp4 --output merged.mp4
```

---

## 输出目录

```text
my_project/
├── color/         彩色帧（PNG 无损，连续编号）
├── lineart/       透明底黑线线稿（正片叠底上色）
├── lineart_white/ 白底黑线版
├── keyframes/     关键帧彩色图与对应线稿
├── depth/         灰度深度图（白=近，黑=远）
├── mask/          主体硬蒙版（白=主体）
├── cutout/        主体透明抠图
├── basecolor/     自动大色块底色
├── preview/       接触表、主色卡、GIF
├── prores/        ProRes MOV
├── video/         原始视频
├── manifest.txt   帧率/帧数/分辨率/目录说明
└── keyframes_index.txt
```

帧文件从 `frame_000001.png` 起连续编号，请勿断号或重排。

---

## 常用参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--fps` | 24 | 抽帧帧率 |
| `--lineart-bg` | transparent | 线稿底色：transparent / white / both |
| `--canny-low` / `--canny-high` | 50 / 150 | Canny 双阈值 |
| `--line-width` | 1 | 线稿线条粗细 |
| `--min-component` | 30 | 碎点过滤面积（像素） |
| `--keyframe-threshold` | 18 | 关键帧 pHash 距离阈值（0–64），调大关键帧更少 |
| `--mask-threshold` | 127 | 主体蒙版阈值，调大更保守 |
| `--color-levels` | 6 | 自动底色的色块层级数 |
| `--palette-k` | 8 | 主色卡聚类颜色数 |

功能开关（加参数即关闭）：

```bash
--no-depth         关闭深度图（跳过模型推理，速度最快）
--no-segment       关闭主体分割
--no-cutout        关闭透明抠图
--no-keyframes     关闭关键帧
--no-stabilize     关闭线稿时域稳定
--no-contact-sheet 关闭接触表
--no-palette       关闭主色卡
--no-base-color    关闭自动底色
--no-gif           关闭 GIF
--no-prores        关闭 ProRes MOV
--no-zip           关闭自动打包
```

示例：

```bash
python3 scripts/extract_frames.py --input source.mp4 --output proj \
  --lineart-bg both --line-width 2 --min-component 50
```

---

## 在其他 AI 平台上使用

本项目是一个标准的 AI Agent Skill，不绑定单一平台，下载后即可迁移：

- **豆包 / 其他豆包系 AI**：将整个目录放入用户技能目录（`user_skills/`），由 `SKILL.md` 与 `agents/doubao.yaml` 自动注册，对话中直接调用「视频帧序列导出」
- **千问（通义 Qwen）及其他兼容 OpenAI 协议的 AI**：参考 `agents/openai.yaml` 中的接口定义接入；技能的核心能力全部以独立 Python 脚本提供，任何支持调用本地脚本/工具的 AI Agent 均可直接编排使用
- **纯命令行使用**：不依赖任何 AI，直接运行 `scripts/` 下的脚本即可完成全部处理

迁移时只需保证：Python 依赖已安装、ffmpeg 可用、已执行 `download_models.py` 拉取模型。

---

## 文档

- [使用说明.md](使用说明.md)：完整操作手册、参数详解与常见问题
- [技术实现.md](技术实现.md)：架构设计、数据流与核心算法原理
- [references/c4d-guide.md](references/c4d-guide.md)：C4D 导入与 2.5D 合成指南

---

## 技术栈

Python 3 · OpenCV · NumPy · Pillow · ONNX Runtime（CPU）· ffmpeg/ffprobe · MiDaS · U2NetP

---

## 性能参考

360p 下深度与分割合计约 0.6 秒/帧（CPU），千帧级约 10 分钟。建议先用 5 秒小样验证画面与参数，再跑全量。

---

## 许可证

[MIT License](LICENSE)
