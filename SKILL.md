---
name: video-frame-exporter
display_name: "视频帧序列导出"
description: "根据一句话提示词自动生成短视频（支持分段生成，最长约1分半、批量处理），并逐帧导出全套素材：彩色帧、透明底黑白线稿帧（可在绘画软件手动上色）、自动提取的关键帧、MiDaS 单目深度图、U2NetP 主体蒙版与透明抠图、自动大色块底色、接触表、主色卡、GIF 预览、ProRes MOV、原始视频与清单文件，全部为连续编号 PNG 序列，可直接导入 Cinema 4D（C4D）做图片序列纹理、2.5D 位移与分层合成。当用户要求一句话/文字生成视频并保存每一帧、导出帧图片、生成黑白线稿或上色底稿、提取关键帧、深度图/蒙版/抠图、为 C4D 准备帧序列素材时使用。"
---

# 视频帧序列导出

## 输出结构

```text
<项目名>/
├── color/         彩色帧（PNG 无损，连续编号）
├── lineart/       透明底黑线线稿（正片叠底上色）
├── lineart_white/ 白底黑线版（--lineart-bg both 时生成）
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

## 工作流

### 1. 分镜确认（生成前必做）

- 解析用户的一句话，先输出简短分镜方案：主体、风格、镜头运动、分段安排，得到用户确认后再生成，避免浪费额度。
- 确认参数：时长（用户每次指定，默认 ≤90 秒）、比例（默认 16:9）、帧率（默认 24fps）。
- 用户提供参考图时改用 `image_to_video` 锁定风格与主体；无参考图用 `text_to_video`。

### 2. 生成视频（分段路由）

默认模型 `seedance_2.0_fast`（单段 4–15 秒），按目标时长 T：

- T ≤15 秒：单段。
- 15 < T ≤30 秒：拆 2 段；或用户明确选定 seedance 2.5（会员模型，消耗更多额度）单段生成。
- T >30 秒：按每段 ≤15 秒拆 N 段，各段共享统一主体与风格描述，段间写明衔接。

多段先拼接：

```bash
python3 scripts/concat_clips.py clip1.mp4 clip2.mp4 ... --output merged.mp4
```

### 3. 下载并全功能抽帧

```bash
curl -L -o source.mp4 "<视频URL>"
python3 scripts/extract_frames.py --input source.mp4 --output "<项目目录>"
```

默认全部功能开启、自动打包 zip。断点续跑：中断后重跑同一命令，已存在的产物自动跳过，不重复计算。多视频批量：`--input a.mp4 b.mp4`，输出独立子目录。

常用调整参数：

```bash
--no-depth --no-segment     关闭深度/分割（跳过模型推理，速度最快）
--lineart-bg both           同时输出透明版与白底版
--line-width 2              线条加粗
--min-component 50          更激进地清理碎点
--keyframe-threshold 25     调大则关键帧更少（pHash 距离，0–64）
--mask-threshold 160        调大则主体蒙版更保守
--color-levels 4            底色块更少更概括
--no-prores --no-gif        关闭对应预览输出
```

### 4. 交付

- 通过 `present_files` 交付 zip 包（必要时附原始视频、GIF）。
- 说明：想省事就只给 keyframes 上色，basecolor 作底色参考；depth/mask/cutout 用于 C4D 立体与合成。
- C4D 具体操作按 `references/c4d-guide.md` 回答。

## 参数默认值

| 参数 | 默认值 | 调整方式 |
|---|---|---|
| 帧率 | 24 fps | `--fps` |
| 比例 | 16:9 | 生成时指定 |
| 线稿底 | 透明底 | `--lineart-bg white/both` |
| Canny 阈值 | 50/150 | `--canny-low/high` |
| 碎点过滤 | 30 像素 | `--min-component` |
| 线宽 | 1 | `--line-width` |
| 关键帧阈值 | pHash 距离 18 | `--keyframe-threshold` |
| 蒙版阈值 | 127 | `--mask-threshold` |
| 底色层级 | 6 色 | `--color-levels` |
| 视频模型 | seedance_2.0_fast | 2.5 需用户明确选定 |

## 模型与性能

- ONNX 模型内置在技能 `models/` 目录（MiDaS 64MB + U2NetP 4.4MB），自包含、无需额外下载；模型损坏时运行 `python3 scripts/download_models.py` 修复。
- 深度与分割在 CPU 上逐帧推理，参考速度约 0.6 秒/帧（360p），千帧级约 10 分钟。长任务建议先用 5 秒小样验证画面与参数，再跑全量；重跑时断点续跑会跳过已完成帧。
