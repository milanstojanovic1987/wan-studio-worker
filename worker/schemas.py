from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class JobSpec(BaseModel):
    model: str = Field(pattern="^(wan22_lightning|wan22_s2v)$")
    prompt: str = Field(min_length=1, max_length=8000)
    width: int = Field(default=832, ge=256, le=2048)
    height: int = Field(default=480, ge=256, le=2048)
    frames: int = Field(default=81, ge=9, le=721)
    fps: int = Field(default=16, ge=1, le=120)
    steps: int = Field(default=4, ge=1, le=100)
    seed: int = Field(default=42, ge=0, le=2**32-1)
    extra: dict = Field(default_factory=dict)

    @field_validator("width", "height")
    @classmethod
    def divisible_by_16(cls, value: int) -> int:
        if value % 16:
            raise ValueError("must be divisible by 16")
        return value


class JobView(BaseModel):
    job_id: str
    status: str
    model: str
    progress: float = 0.0
    message: str = ""
    error: str = ""
    result_name: str = ""
