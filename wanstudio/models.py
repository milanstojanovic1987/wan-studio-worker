from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Scene:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    title: str = "Scene"
    image_path: str = ""
    motion_prompt: str = ""
    dialogue: str = ""
    audio_path: str = ""
    voice: str = "af_heart"
    seed: int = 42
    status: str = "pending"
    output_path: str = ""
    remote_job_id: str = ""
    error: str = ""

    @property
    def mode(self) -> str:
        return "wan22_s2v" if self.dialogue.strip() or self.audio_path else "wan22_lightning"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Project:
    name: str
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "scenes": [s.to_dict() for s in self.scenes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        return cls(name=data.get("name", "Project"), scenes=[Scene.from_dict(x) for x in data.get("scenes", [])])
