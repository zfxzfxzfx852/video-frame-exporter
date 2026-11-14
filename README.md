# 视频帧序列导出 video-frame-exporter

一句话生成短视频，并逐帧导出全套制作素材：彩色帧、透明底黑白线稿、关键帧、MiDaS 单目深度图、U2NetP 主体蒙版与透明抠图、自动大色块底色、接触表、主色卡、GIF 预览、ProRes MOV 与清单文件。全部为连续编号 PNG 序列，可直接导入 Cinema 4D（C4D）做图片序列纹理、2.5D 位移与分层合成。

提供 **Web 图形界面、REST API、命令行** 三种使用方式，全程本地运行，无需 GPU；模型通过 ONNX Runtime 推理，CPU/GPU 自动切换。

---

## 功能特性

- **三种使用方式**：Web 界面（拖拽上传 + 实时进度 + 在线预览）、REST API、命令行
- 视频生成与分段拼接：支持 4–15 秒分段生成，自动拼接为最长约 90 秒的完整视频
- 彩色帧序列：ffmpeg 按目标帧率抽帧，PNG 无损、连续编号
- 黑白线稿：双边滤波 + Canny 边缘，三帧时域投票抑制闪烁，连通域清理与线宽可调，输出透明底 / 白底两个版本
- 关键帧提取：基于感知哈希（pHash）贪心选择，减少上色工作量
- 单目深度图：MiDaS 模型输出相对深度，用于 C4D 位移与 2.5D 视差
- 主体蒙版与抠图：U2NetP 输出软/硬蒙版，一步生成带透明通道的 BGRA 抠图
- 自动底色：均值漂移 + KMeans 量化大色块，线稿边缘自动压黑
- 预览产物：接触表、主色卡、GIF、ProRes 10bit MOV；Web 端内置帧序列播放器与前后对比滑块
- 参数预设：动漫风 / 写实风 / 纯线稿 / 极速模式 一键切换
- 多进程帧池：按 CPU 核数并行推理，显著提速
- 断点续跑：中断后重跑同一命令，已完成产物自动跳过
- 批量处理：一次传入多个视频，输出独立子目录

---

## 快速开始

### 方式一：Docker 一键启动（推荐）

```bash
docker compose up -d
```

浏览器打开 `http://localhost:8000` 即可使用 Web 界面，镜像内已包含 ffmpeg 与全部模型。

### 方式二：本地安装

环境要求：Python 3.10+、ffmpeg/ffprobe（需在 PATH 中），支持 Windows / macOS / Linux。

```bash
git clone https://github.com/zfxzfxzfx852/video-frame-exporter.git
cd video-frame-exporter
pip install -r requirements.txt
python3 scripts/download_models.py        # 下载模型（约 68MB）
```

启动 Web 界面：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000`：上传视频 → 选择预设或自定义参数 → 实时查看进度 → 在线预览并下载 zip。

### 方式三：命令行

```bash
# 全功能导出
python3 scripts/extract_frames.py --input source.mp4 --output my_project

# 使用预设 + 多进程加速
python3 scripts/extract_frames.py --input source.mp4 --output my_project \
  --preset anime --workers 4

# 多视频批量
python3 scripts/extract_frames.py --input a.mp4 b.mp4 c.mp4 --output batch_dir

# 多段视频拼接
python3 scripts/concat_clips.py clip1.mp4 clip2.mp4 --output merged.mp4
```

也可通过配置文件运行：`--config params.yaml`（或 `.json`）。

---

## REST API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs` | multipart 上传视频与参数，创建任务 |
| GET | `/api/jobs` | 任务列表 |
| GET | `/api/jobs/{id}` | 任务状态与进度 |
| GET | `/api/jobs/{id}/events` | SSE 实时进度推送 |
| GET | `/api/jobs/{id}/dirs` | 输出目录及文件数 |
| GET | `/api/jobs/{id}/files/{dir}` | 目录内文件列表 |
| GET | `/api/jobs/{id}/raw/{dir}/{file}` | 原始图片 |
| GET | `/api/jobs/{id}/download` | 下载结果 zip |

完整交互式文档：服务启动后访问 `http://localhost:8000/docs`。

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
| `--preset` | 无 | anime / realistic / sketch_only / fast |
| `--lineart-bg` | transparent | transparent / white / both |
| `--canny-low` / `--canny-high` | 50 / 150 | Canny 双阈值 |
| `--line-width` | 1 | 线稿线条粗细 |
| `--min-component` | 30 | 碎点过滤面积（像素） |
| `--keyframe-threshold` | 18 | 关键帧 pHash 距离阈值（0–64），调大关键帧更少 |
| `--mask-threshold` | 127 | 主体蒙版阈值，调大更保守 |
| `--color-levels` | 6 | 自动底色的色块层级数 |
| `--workers` | 1 | 多进程帧池工作数 |
| `--config` | 无 | JSON/YAML 配置文件 |

功能开关（加参数即关闭）：`--no-depth` `--no-segment` `--no-cutout` `--no-keyframes` `--no-stabilize` `--no-contact-sheet` `--no-palette` `--no-base-color` `--no-gif` `--no-prores` `--no-zip`

---

## 在其他 AI 平台上使用

本项目是标准的 AI Agent Skill，不绑定单一平台：

- **豆包 / 其他豆包系 AI**：将整个目录放入用户技能目录（`user_skills/`），由 `SKILL.md` 与 `agents/doubao.yaml` 自动注册
- **千问（通义 Qwen）及其他兼容 OpenAI 协议的 AI**：参考 `agents/openai.yaml` 接入；核心能力全部以独立 Python 脚本提供，任何支持调用本地工具的 AI Agent 均可直接编排
- **纯命令行 / Web / API**：不依赖任何 AI 即可使用

迁移时保证：Python 依赖已安装、ffmpeg 可用、已执行 `download_models.py`。

---

## 文档

- [使用说明.md](使用说明.md)：完整操作手册、参数详解与常见问题
- [技术实现.md](技术实现.md)：架构设计、数据流与核心算法原理
- [references/c4d-guide.md](references/c4d-guide.md)：C4D 导入与 2.5D 合成指南

---

## 技术栈

Python 3 · FastAPI · OpenCV · NumPy · Pillow · ONNX Runtime（CPU/GPU 自动切换）· ffmpeg/ffprobe · MiDaS · U2NetP · Docker

---

## 性能参考

360p 下深度与分割合计约 0.6 秒/帧（单进程 CPU），多进程帧池可近线性提速；千帧级约 10 分钟。建议先用少量帧或极速模式验证参数，再跑全量。

---

## 许可证

[MIT License](LICENSE)
