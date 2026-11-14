"""任务管理：后台线程运行处理管线，维护进度与状态。"""
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict

from video_frame_exporter.config import ExportConfig
from video_frame_exporter.pipeline import batch_process
from video_frame_exporter.logging_utils import get_logger

logger = get_logger()

DATA_ROOT = os.environ.get("VFE_DATA_ROOT",
                           os.path.join(os.path.dirname(os.path.dirname(
                               os.path.abspath(__file__))), "data"))


@dataclass
class Job:
    id: str
    name: str
    status: str = "queued"              # queued / running / done / error
    progress: float = 0.0
    phase: str = ""
    done_frames: int = 0
    total_frames: int = 0
    output_dir: str = ""
    zip_path: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "status": self.status,
            "progress": round(self.progress, 2), "phase": self.phase,
            "done_frames": self.done_frames, "total_frames": self.total_frames,
            "error": self.error,
        }


_JOBS: Dict[str, Job] = {}
_LOCK = threading.Lock()


def list_jobs() -> Dict[str, Job]:
    return dict(_JOBS)


def get_job(job_id: str) -> Job:
    if job_id not in _JOBS:
        raise KeyError(job_id)
    return _JOBS[job_id]


def create_job(filename: str, video_path: str, config: ExportConfig) -> Job:
    job_id = uuid.uuid4().hex[:12]
    output_dir = os.path.join(DATA_ROOT, job_id, "output")
    job = Job(id=job_id, name=filename, output_dir=output_dir)
    with _LOCK:
        _JOBS[job_id] = job

    def progress_cb(done, total, phase):
        job.done_frames = done
        job.total_frames = total
        job.progress = done / total * 100 if total else 0
        job.phase = phase

    def runner():
        job.status = "running"
        try:
            # 关闭管线内部自动打包，由任务完成后统一确认 zip 路径
            config.zip_output = True
            result = batch_process([video_path], output_dir, config, progress_cb)
            job.zip_path = result.get("zip", "")
            job.progress = 100.0
            job.status = "done"
            logger.info("任务完成 %s", job_id)
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            logger.exception("任务失败 %s", job_id)

    threading.Thread(target=runner, daemon=True, name=f"job-{job_id}").start()
    return job
