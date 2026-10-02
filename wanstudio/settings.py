from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Settings:
    worker_image: str = "ghcr.io/YOUR_GITHUB_USERNAME/wan-studio-worker:latest"
    gpu_id: str = "NVIDIA A100 80GB PCIe"
    cloud: str = "COMMUNITY"
    disk_gb: int = 200
    projects_root: str = str(Path.home() / "WanStudioProjects")
    idle_exit_seconds: int = 900

    @property
    def config_dir(self) -> Path:
        root = Path(os.getenv("APPDATA", Path.home())) / "WanStudio"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def path(self) -> Path:
        return self.config_dir / "settings.json"

    def save(self) -> None:
        self.path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "Settings":
        probe = cls()
        if not probe.path.is_file():
            return probe
        try:
            raw = json.loads(probe.path.read_text(encoding="utf-8"))
            allowed = set(cls.__dataclass_fields__)
            return cls(**{k: v for k, v in raw.items() if k in allowed})
        except Exception:
            return probe
