from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from worker.jobs import JobManager
from worker.schemas import JobSpec, JobView

app = FastAPI(title="Wan Studio Worker", version="0.1.0")
manager = JobManager(Path(os.getenv("STUDIO_JOB_ROOT", "/workspace/studio_jobs")))


def authorize(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("STUDIO_WORKER_TOKEN", "")
    if not expected: raise HTTPException(status_code=503, detail="Worker token is not configured")
    if authorization != f"Bearer {expected}": raise HTTPException(status_code=401, detail="Invalid worker token")
    manager.touch()


@app.get("/health")
def health(_: None = Depends(authorize)) -> dict:
    return {"ok": True, "queue_depth": manager.pending.qsize(), "running_jobs": manager.running_jobs}


@app.get("/v1/models")
def models(_: None = Depends(authorize)) -> dict:
    return {"models": [{"id":"wan22_lightning","audio":False},{"id":"wan22_s2v","audio":True}]}


@app.post("/v1/jobs", response_model=JobView)
def submit_job(spec: str = Form(...), image: UploadFile = File(...), audio: UploadFile | None = File(default=None), _: None = Depends(authorize)) -> JobView:
    try: parsed = JobSpec.model_validate(json.loads(spec))
    except Exception as exc: raise HTTPException(status_code=422, detail=f"Invalid job spec: {exc}") from exc
    temp = Path(tempfile.mkdtemp(prefix="wanstudio-upload-"))
    try:
        image_path = _save(image, temp)
        audio_path = _save(audio, temp) if audio else None
        return JobView(**manager.create(parsed, image_path, audio_path).__dict__)
    finally: shutil.rmtree(temp, ignore_errors=True)


@app.get("/v1/jobs/{job_id}", response_model=JobView)
def job(job_id: str, _: None = Depends(authorize)) -> JobView:
    try: return JobView(**manager.get(job_id).__dict__)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/v1/jobs/{job_id}/result")
def result(job_id: str, _: None = Depends(authorize)) -> FileResponse:
    try: path = manager.result(job_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail="Job not found") from exc
    except RuntimeError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}.mp4")


def _save(upload: UploadFile, directory: Path) -> Path:
    target = directory / ("upload" + Path(upload.filename or "file.bin").suffix.lower())
    with target.open("wb") as fh: shutil.copyfileobj(upload.file, fh)
    return target


def _idle_watchdog():
    seconds = int(os.getenv("STUDIO_IDLE_EXIT_SECONDS", "900"))
    while True:
        time.sleep(15)
        if manager.running_jobs == 0 and manager.pending.qsize() == 0 and time.monotonic() - manager.last_activity > seconds:
            os._exit(0)

threading.Thread(target=_idle_watchdog, daemon=True, name="idle-exit-watchdog").start()
