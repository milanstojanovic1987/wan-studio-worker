from __future__ import annotations

import json
import queue
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from worker.backends import Wan22LightningBackend, Wan22S2VBackend
from worker.schemas import JobSpec


@dataclass
class Job:
    job_id: str
    status: str
    model: str
    progress: float = 0.0
    message: str = "Queued"
    error: str = ""
    result_name: str = ""


class JobManager:
    def __init__(self, root: Path):
        self.root = root; self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}; self.specs: dict[str, JobSpec] = {}; self.pending: queue.Queue[str] = queue.Queue(); self.lock = threading.Lock()
        self.backends = {"wan22_lightning": Wan22LightningBackend(), "wan22_s2v": Wan22S2VBackend()}
        self.last_activity = time.monotonic(); self.running_jobs = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def touch(self): self.last_activity = time.monotonic()

    def create(self, spec: JobSpec, image_source: Path, audio_source: Path | None) -> Job:
        self.touch(); job_id = uuid4().hex; directory = self.root / job_id; directory.mkdir()
        image_target = directory / ("input_image" + image_source.suffix.lower()); shutil.copy2(image_source, image_target)
        if audio_source: shutil.copy2(audio_source, directory / ("input_audio" + audio_source.suffix.lower()))
        (directory / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        job = Job(job_id, "queued", spec.model)
        with self.lock: self.jobs[job_id] = job; self.specs[job_id] = spec
        self._persist(job); self.pending.put(job_id); return job

    def get(self, job_id: str) -> Job:
        self.touch()
        with self.lock: job = self.jobs.get(job_id)
        if job: return job
        path = self.root / job_id / "job.json"
        if not path.is_file(): raise KeyError(job_id)
        return Job(**json.loads(path.read_text(encoding="utf-8")))

    def result(self, job_id: str) -> Path:
        self.touch(); job = self.get(job_id)
        if job.status != "succeeded": raise RuntimeError(f"Job is {job.status}")
        return self.root / job_id / job.result_name

    def _update(self, job: Job, progress: float, message: str):
        job.progress = max(0, min(1, progress)); job.message = message; self._persist(job)

    def _worker(self):
        while True:
            job_id = self.pending.get()
            try: self._run(job_id)
            finally: self.pending.task_done()

    def _run(self, job_id: str):
        job = self.jobs[job_id]; spec = self.specs[job_id]; directory = self.root / job_id
        image = next(directory.glob("input_image.*")); audio = next(iter(directory.glob("input_audio.*")), None)
        job.status = "running"; job.message = "Starting"; self.running_jobs += 1; self._persist(job)
        try:
            if spec.model == "wan22_s2v":
                # S2V runs in a separate process. Release any cached I2V pipeline first
                # so the two 14B models do not coexist in RAM/VRAM.
                import gc
                from worker.backends.wan_i2v import Wan22LightningBackend
                Wan22LightningBackend._pipe = None
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
            output = self.backends[spec.model].generate(spec, directory, image, audio, lambda p, m: self._update(job, p, m))
            job.result_name = output.name; job.status = "succeeded"; job.progress = 1.0; job.message = "Finished"
        except Exception as exc:
            job.status = "failed"; job.error = f"{type(exc).__name__}: {exc}"; job.message = "Failed"
        finally:
            self.running_jobs -= 1; self.touch(); self._persist(job)

    def _persist(self, job: Job):
        (self.root / job.job_id / "job.json").write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
