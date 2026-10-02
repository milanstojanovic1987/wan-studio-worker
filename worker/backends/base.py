from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from worker.schemas import JobSpec

Progress = Callable[[float, str], None]


class Backend(ABC):
    @abstractmethod
    def generate(self, spec: JobSpec, workdir: Path, image: Path, audio: Path | None, progress: Progress) -> Path:
        raise NotImplementedError

    @staticmethod
    def run(command: list[str], cwd: Path, progress: Progress, env: dict[str, str] | None = None) -> None:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        proc = subprocess.Popen(command, cwd=str(cwd), env=merged, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        tail: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line:
                tail.append(line); tail = tail[-80:]
                progress(0.25, line[-500:])
        code = proc.wait()
        if code:
            raise RuntimeError(f"Model process exited with code {code}:\n" + "\n".join(tail[-20:]))
