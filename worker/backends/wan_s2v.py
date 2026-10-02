from __future__ import annotations

import os
import sys
from pathlib import Path

from worker.backends.base import Backend, Progress
from worker.schemas import JobSpec


class Wan22S2VBackend(Backend):
    def _model_dir(self, progress: Progress) -> Path:
        target = Path(os.getenv("WAN_S2V_MODEL", "/workspace/models/Wan2.2-S2V-14B"))
        marker = target / "configuration.json"
        if not target.exists() or not any(target.iterdir()):
            progress(0.02, "Downloading Wan 2.2 S2V model (first dialogue scene is slower)...")
            from huggingface_hub import snapshot_download
            target.mkdir(parents=True, exist_ok=True)
            snapshot_download(repo_id="Wan-AI/Wan2.2-S2V-14B", local_dir=str(target))
        return target

    @staticmethod
    def _tts(text: str, voice: str, output: Path, progress: Progress) -> Path:
        progress(0.05, f"Creating dialogue audio with Kokoro ({voice})...")
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code="a")
        chunks = [audio for _, _, audio in pipeline(text, voice=voice or "af_heart", speed=1.0, split_pattern=r"\n+")]
        if not chunks:
            raise RuntimeError("Kokoro returned no audio.")
        sf.write(output, np.concatenate(chunks), 24000)
        return output

    def generate(self, spec: JobSpec, workdir: Path, image: Path, audio: Path | None, progress: Progress) -> Path:
        repo = Path(os.getenv("WAN_REPO", "/opt/Wan2.2"))
        if not (repo / "generate.py").is_file():
            raise RuntimeError("Wan2.2 repository is missing from the worker image.")
        model = self._model_dir(progress)
        dialogue = str(spec.extra.get("dialogue") or "").strip()
        voice = str(spec.extra.get("voice") or "af_heart")
        if audio is None:
            if not dialogue:
                raise ValueError("Speech-to-video requires dialogue text or an audio file.")
            audio = self._tts(dialogue, voice, workdir / "dialogue.wav", progress)
        output = workdir / "result.mp4"
        progress(0.08, "Generating Wan 2.2 speech-to-video clip with lip sync...")
        command = [
            sys.executable, str(repo / "generate.py"),
            "--task", "s2v-14B",
            "--size", f"{spec.width}*{spec.height}",
            "--ckpt_dir", str(model),
            "--prompt", spec.prompt,
            "--image", str(image),
            "--audio", str(audio),
            "--offload_model", "True",
            "--convert_model_dtype",
            "--infer_frames", "80",
            "--base_seed", str(spec.seed),
            "--save_file", str(output),
        ]
        self.run(command, repo, progress)
        if not output.is_file():
            raise RuntimeError("Wan S2V finished without producing result.mp4.")
        return output
