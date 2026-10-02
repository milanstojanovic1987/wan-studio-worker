from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .models import Project, Scene


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return value or "project"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        return sorted([p.name for p in self.root.iterdir() if p.is_dir() and (p / "project.json").is_file()], key=str.lower)

    def project_dir(self, name: str) -> Path:
        return self.root / safe_name(name)

    def create(self, name: str) -> Project:
        name = safe_name(name)
        directory = self.project_dir(name)
        if (directory / "project.json").exists():
            raise FileExistsError(f"Project already exists: {name}")
        (directory / "inputs").mkdir(parents=True, exist_ok=True)
        (directory / "outputs").mkdir(exist_ok=True)
        project = Project(name=name)
        self.save(project)
        return project

    def load(self, name: str) -> Project:
        path = self.project_dir(name) / "project.json"
        if not path.is_file():
            raise FileNotFoundError(name)
        return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, project: Project) -> None:
        directory = self.project_dir(project.name)
        (directory / "inputs").mkdir(parents=True, exist_ok=True)
        (directory / "outputs").mkdir(exist_ok=True)
        target = directory / "project.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(target)

    def import_asset(self, project: Project, source: str | Path, scene: Scene, kind: str) -> str:
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError(src)
        suffix = src.suffix.lower()
        dst = self.project_dir(project.name) / "inputs" / f"{scene.id}_{kind}{suffix}"
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return str(dst)
