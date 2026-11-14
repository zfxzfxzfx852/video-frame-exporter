"""FastAPI 后端：上传、任务管理、SSE 进度、文件预览与下载。"""
import asyncio
import json
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from video_frame_exporter.config import ExportConfig
from app import tasks

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="video-frame-exporter API", version="2.0.0")

BOOLEAN_FIELDS = {"keyframes", "stabilize", "contact_sheet", "palette",
                  "base_color", "depth", "segment", "cutout", "gif",
                  "prores", "zip_output", "depth_invert"}
INT_FIELDS = {"canny_low", "canny_high", "line_width", "min_component",
               "keyframe_threshold", "mask_threshold", "color_levels",
               "palette_k", "workers"}
NUMERIC_FIELDS = BOOLEAN_FIELDS | INT_FIELDS | {"fps"}


def _build_config(form, preset: str = "") -> ExportConfig:
    config = ExportConfig.from_preset(preset) if preset else ExportConfig()
    for key in form.keys():
        if key not in ExportConfig.__dataclass_fields__:
            continue
        raw = form.get(key)
        if key in BOOLEAN_FIELDS:
            setattr(config, key, str(raw).lower() in ("1", "true", "on", "yes"))
        elif key in INT_FIELDS:
            setattr(config, key, int(raw))
        elif key == "fps":
            setattr(config, key, float(raw))
        else:
            setattr(config, key, raw)
    return config


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(request: Request):
    form = await request.form()
    upload = form.get("file")
    if upload is None or not upload.filename:
        raise HTTPException(400, "缺少视频文件")
    upload_dir = os.path.join(tasks.DATA_ROOT, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, os.path.basename(upload.filename))
    with open(dest, "wb") as f:
        f.write(await upload.read())
    preset = form.get("preset", "")
    config = _build_config(form, preset)
    job = tasks.create_job(upload.filename, dest, config)
    return job.to_dict()


@app.get("/api/jobs")
def get_jobs():
    return [j.to_dict() for j in tasks.list_jobs().values()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _safe_job(job_id).to_dict()


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = _safe_job(job_id)

    async def stream():
        last = None
        while True:
            data = job.to_dict()
            if data != last:
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                last = data
            if job.status in ("done", "error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/dirs")
def job_dirs(job_id: str):
    job = _safe_job(job_id)
    return {name: len(os.listdir(os.path.join(job.output_dir, name)))
            for name in os.listdir(job.output_dir)
            if os.path.isdir(os.path.join(job.output_dir, name))}


@app.get("/api/jobs/{job_id}/files/{dir_name}")
def list_files(job_id: str, dir_name: str):
    path = os.path.join(_safe_job(job_id).output_dir, dir_name)
    if not os.path.isdir(path):
        raise HTTPException(404, "目录不存在")
    return sorted(os.listdir(path))


@app.get("/api/jobs/{job_id}/raw/{dir_name}/{file_name}")
def raw_file(job_id: str, dir_name: str, file_name: str):
    path = os.path.join(_safe_job(job_id).output_dir, dir_name,
                        os.path.basename(file_name))
    if not os.path.isfile(path):
        raise HTTPException(404, "文件不存在")
    return FileResponse(path)


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str):
    job = _safe_job(job_id)
    if job.status != "done" or not job.zip_path or not os.path.isfile(job.zip_path):
        raise HTTPException(400, "zip 尚未生成")
    return FileResponse(job.zip_path, filename=f"{job_id}.zip")


def _safe_job(job_id: str) -> tasks.Job:
    try:
        return tasks.get_job(job_id)
    except KeyError:
        raise HTTPException(404, "任务不存在")


app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")),
          name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
