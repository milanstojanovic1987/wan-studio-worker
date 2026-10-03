from __future__ import annotations

import os
import threading
from pathlib import Path

from worker.backends.base import Backend, Progress
from worker.schemas import JobSpec


class Wan22LightningBackend(Backend):
    _pipe = None
    _lock = threading.Lock()

    @staticmethod
    def _load_loras(pipe) -> None:
        repo = "lightx2v/Wan2.2-Lightning"
        folder = "Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1"
        pipe.load_lora_weights(repo, weight_name=f"{folder}/high_noise_model.safetensors", adapter_name="lightning_high")
        pipe.load_lora_weights(repo, weight_name=f"{folder}/low_noise_model.safetensors", adapter_name="lightning_low", load_into_transformer_2=True)
        pipe.set_adapters(["lightning_high", "lightning_low"], adapter_weights=[1.0, 1.0])
        pipe.fuse_lora(components=["transformer"], lora_scale=1.0, adapter_names=["lightning_high"])
        pipe.fuse_lora(components=["transformer_2"], lora_scale=1.0, adapter_names=["lightning_low"])
        pipe.unload_lora_weights()

    def _load(self, progress: Progress):
        if self.__class__._pipe is not None:
            return self.__class__._pipe
        with self.__class__._lock:
            if self.__class__._pipe is not None:
                return self.__class__._pipe
            progress(0.02, "Downloading/loading Wan 2.2 Lightning (first scene is slower)...")
            import torch
            from diffusers import WanImageToVideoPipeline, WanTransformer3DModel

            model_id = os.getenv("WAN_MODEL_ID", "Wan-AI/Wan2.2-I2V-A14B-Diffusers")
            transformer_id = os.getenv("WAN_TRANSFORMER_ID", "Wan-AI/Wan2.2-I2V-A14B-Diffusers")
            high = WanTransformer3DModel.from_pretrained(transformer_id, subfolder="transformer", torch_dtype=torch.bfloat16)
            low = WanTransformer3DModel.from_pretrained(transformer_id, subfolder="transformer_2", torch_dtype=torch.bfloat16)
            pipe = WanImageToVideoPipeline.from_pretrained(model_id, transformer=high, transformer_2=low, torch_dtype=torch.bfloat16)
            self._load_loras(pipe)
            pipe.enable_model_cpu_offload()
            self.__class__._pipe = pipe
            return pipe

    def generate(self, spec: JobSpec, workdir: Path, image: Path, audio: Path | None, progress: Progress) -> Path:
        if spec.steps != 4:
            raise ValueError("Wan 2.2 Lightning requires exactly four steps.")
        import torch
        from diffusers.utils import export_to_video, load_image

        pipe = self._load(progress)
        source = load_image(str(image)).convert("RGB").resize((spec.width, spec.height))
        progress(0.08, "Generating Wan 2.2 Lightning clip...")
        frames = pipe(
            image=source,
            prompt=spec.prompt,
            height=spec.height,
            width=spec.width,
            num_frames=spec.frames,
            guidance_scale=1.0,
            guidance_scale_2=1.0,
            num_inference_steps=4,
            generator=torch.Generator(device="cuda").manual_seed(spec.seed),
        ).frames[0]
        output = workdir / "result.mp4"
        export_to_video(frames, str(output), fps=spec.fps)
        return output
