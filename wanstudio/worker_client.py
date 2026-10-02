from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import requests


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _json(self, response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise WorkerError(f"Worker returned HTTP {response.status_code} with non-JSON content.") from exc
        if not response.ok:
            raise WorkerError(f"Worker HTTP {response.status_code}: {data.get('detail', data)}")
        return data

    def health(self) -> dict[str, Any]:
        return self._json(self.session.get(self.base_url + "/health", timeout=30))

    def wait_ready(self, progress: Callable[[str], None] | None = None, timeout_seconds: int = 900) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if self.health().get("ok"):
                    return
            except Exception:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("The RunPod worker did not become reachable.")
            if progress:
                progress("Waiting for the Wan worker...")
            time.sleep(5)

    def submit(self, spec: dict[str, Any], image_path: str, audio_path: str = "") -> str:
        handles = []
        files: dict[str, tuple] = {"spec": (None, json.dumps(spec), "application/json")}
        try:
            image = open(image_path, "rb")
            handles.append(image)
            files["image"] = (Path(image_path).name, image)
            if audio_path:
                audio = open(audio_path, "rb")
                handles.append(audio)
                files["audio"] = (Path(audio_path).name, audio)
            response = self.session.post(self.base_url + "/v1/jobs", files=files, timeout=180)
            return self._json(response)["job_id"]
        finally:
            for handle in handles:
                handle.close()

    def wait_job(self, job_id: str, progress: Callable[[str], None] | None = None, timeout_seconds: int = 7200) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            result = self._json(self.session.get(f"{self.base_url}/v1/jobs/{job_id}", timeout=30))
            if progress:
                progress(result.get("message") or result.get("status") or "Working...")
            if result.get("status") == "succeeded":
                return result
            if result.get("status") == "failed":
                raise WorkerError(result.get("error") or "Generation failed.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Generation is still running after two hours.")
            time.sleep(5)

    def download(self, job_id: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".part")
        try:
            with self.session.get(f"{self.base_url}/v1/jobs/{job_id}/result", stream=True, timeout=900) as response:
                if not response.ok:
                    self._json(response)
                with temp.open("wb") as fh:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            if not temp.is_file() or temp.stat().st_size < 1024:
                raise WorkerError("Downloaded video is empty or invalid.")
            temp.replace(destination)
            return destination
        finally:
            temp.unlink(missing_ok=True)
