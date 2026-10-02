from __future__ import annotations

import time
from typing import Any, Callable
from urllib.parse import quote

import requests


class RunPodError(RuntimeError):
    pass


class RunPodV2:
    """Minimal RunPod REST API v2 client for temporary Pods."""

    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key.strip():
            raise ValueError("Enter your RunPod API key.")
        self.base_url = "https://api.runpod.io/v2"
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"})
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs) -> Any:
        response = self.session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        try:
            payload = response.json() if response.content else {}
        except ValueError as exc:
            raise RunPodError(f"RunPod returned HTTP {response.status_code} with non-JSON content.") from exc
        if not response.ok:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            raise RunPodError(f"RunPod HTTP {response.status_code}: {detail or payload}")
        return payload

    def test_connection(self) -> str:
        self._request("GET", "/pods")
        return "RunPod API connected. No Pod was started."

    def create_temporary_pod(
        self,
        *,
        image: str,
        gpu_id: str,
        cloud: str,
        disk_gb: int,
        worker_token: str,
        idle_exit_seconds: int,
    ) -> dict[str, Any]:
        if not image or "YOUR_GITHUB_USERNAME" in image:
            raise ValueError("Set the published worker image in Settings first.")
        body = {
            "name": f"wan-studio-{int(time.time())}",
            "image": image.strip(),
            "gpu": {"id": gpu_id.strip(), "count": 1},
            "disk": int(disk_gb),
            "ports": ["8000/http"],
            "env": {
                "STUDIO_WORKER_TOKEN": worker_token,
                "STUDIO_WORKER_PORT": "8000",
                "STUDIO_IDLE_EXIT_SECONDS": str(int(idle_exit_seconds)),
                "HF_HOME": "/workspace/.cache/huggingface",
            },
            "mounts": {},
            "cloud": cloud.upper(),
        }
        return self._request("POST", "/pods", json=body)

    def get_pod(self, pod_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pods/{quote(pod_id, safe='')}")

    def terminate(self, pod_id: str) -> None:
        self._request("DELETE", f"/pods/{quote(pod_id, safe='')}")

    def wait_running(self, pod_id: str, progress: Callable[[str], None] | None = None, timeout_seconds: int = 900) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            pod = self.get_pod(pod_id)
            status = str(pod.get("status") or "UNKNOWN")
            if progress:
                progress(f"RunPod Pod: {status.lower()}...")
            if status == "RUNNING":
                return pod
            if status in {"ERROR", "TERMINATED"}:
                raise RunPodError(f"Pod entered {status} before becoming ready.")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Pod did not become ready within {timeout_seconds // 60} minutes.")
            time.sleep(5)


def worker_url(pod_id: str) -> str:
    return f"https://{pod_id}-8000.proxy.runpod.net"
