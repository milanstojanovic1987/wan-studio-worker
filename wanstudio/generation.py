from __future__ import annotations

import secrets
from pathlib import Path
from typing import Callable

from .models import Project
from .runpod import RunPodV2, worker_url
from .settings import Settings
from .store import ProjectStore
from .worker_client import WorkerClient


def run_batch(store: ProjectStore, project: Project, api_key: str, settings: Settings,
              progress: Callable[[str], None] | None = None) -> str:
    scenes = project.scenes
    if not scenes:
        raise ValueError("Add at least one scene.")
    for scene in scenes:
        if not scene.image_path or not Path(scene.image_path).is_file():
            raise ValueError(f"{scene.title}: choose a starting image.")
        if not scene.motion_prompt.strip():
            raise ValueError(f"{scene.title}: enter a motion prompt.")
        if scene.audio_path and not Path(scene.audio_path).is_file():
            raise ValueError(f"{scene.title}: the selected audio file is missing.")

    pending = [s for s in scenes if not (s.output_path and Path(s.output_path).is_file())]
    # Group by backend to avoid repeatedly unloading/reloading multi-GB models.
    pending.sort(key=lambda s: 0 if s.mode == "wan22_lightning" else 1)
    if not pending:
        return "All scenes already have local videos."

    token = secrets.token_urlsafe(32)
    runpod = RunPodV2(api_key)
    pod_id = ""
    terminate_error = ""
    try:
        if progress:
            progress("Creating temporary RunPod Pod (persistent storage disabled)...")
        pod = runpod.create_temporary_pod(
            image=settings.worker_image,
            gpu_id=settings.gpu_id,
            cloud=settings.cloud,
            disk_gb=settings.disk_gb,
            worker_token=token,
            idle_exit_seconds=settings.idle_exit_seconds,
        )
        pod_id = str(pod.get("id") or "")
        if not pod_id:
            raise RuntimeError("RunPod did not return a Pod ID.")
        runpod.wait_running(pod_id, progress=progress)
        worker = WorkerClient(worker_url(pod_id), token)
        worker.wait_ready(progress=progress)

        generated = 0
        for index, scene in enumerate(pending, 1):
            scene.status = "submitting"
            scene.error = ""
            store.save(project)
            if progress:
                kind = "speech-to-video" if scene.mode == "wan22_s2v" else "image-to-video"
                progress(f"{scene.title}: starting {kind} ({index}/{len(pending)})...")
            spec = {
                "model": scene.mode,
                "prompt": scene.motion_prompt.strip(),
                "width": 832,
                "height": 480,
                "frames": 81,
                "fps": 16,
                "steps": 4,
                "seed": int(scene.seed),
                "extra": {"dialogue": scene.dialogue.strip(), "voice": scene.voice},
            }
            try:
                job_id = worker.submit(spec, scene.image_path, scene.audio_path)
                scene.remote_job_id = job_id
                scene.status = "running"
                store.save(project)
                worker.wait_job(job_id, progress=(lambda msg, title=scene.title: progress(f"{title}: {msg}") if progress else None))
                output = store.project_dir(project.name) / "outputs" / f"{scene.id}.mp4"
                worker.download(job_id, output)
                scene.output_path = str(output)
                scene.status = "succeeded"
                scene.error = ""
                generated += 1
                store.save(project)
            except Exception as exc:
                scene.status = "failed"
                scene.error = f"{type(exc).__name__}: {exc}"
                store.save(project)
                raise
        return f"Generated and downloaded {generated} scene(s)."
    finally:
        if pod_id:
            if progress:
                progress("Terminating RunPod Pod...")
            try:
                runpod.terminate(pod_id)
                if progress:
                    progress("RunPod Pod terminated. GPU session ended.")
            except Exception as exc:
                terminate_error = f"WARNING: automatic termination failed: {type(exc).__name__}: {exc}"
                if progress:
                    progress(terminate_error)
        if terminate_error and not any(s.status == "failed" for s in scenes):
            # Keep a visible warning in project state without hiding successful output paths.
            scenes[-1].error = terminate_error
            store.save(project)
