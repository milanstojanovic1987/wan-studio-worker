FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    STUDIO_JOB_ROOT=/workspace/studio_jobs \
    WAN_REPO=/opt/Wan2.2

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg build-essential ninja-build \
    && rm -rf /var/lib/apt/lists/*

# RunPod's PyTorch base may contain a FlashAttention binary compiled against a
# different torch build.  That produces an undefined-symbol crash while merely
# importing Transformers/CLIP.  Wan 2.2 and PyTorch can fall back to SDPA, so
# remove FlashAttention instead of loading an ABI-incompatible extension.
RUN python -m pip uninstall -y flash-attn flash_attn || true

WORKDIR /opt/wan-studio
COPY worker ./worker

RUN python -m pip install --upgrade pip wheel setuptools && \
    python -m pip install --no-cache-dir -r worker/requirements.txt

RUN git clone --depth 1 https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2 && \
    grep -v -E '^[[:space:]]*flash_attn([[:space:]]|$)' /opt/Wan2.2/requirements.txt > /tmp/wan-requirements.txt && \
    python -m pip install --no-cache-dir -r /tmp/wan-requirements.txt && \
    python -m pip install --no-cache-dir -r /opt/Wan2.2/requirements_s2v.txt && \
    python -m pip uninstall -y flash-attn flash_attn || true

# Fail the image build now if the exact imports that failed on RunPod are broken.
RUN python - <<'PY'
import importlib.util
if importlib.util.find_spec("flash_attn") is not None:
    raise RuntimeError("flash_attn unexpectedly remains installed")
from transformers.models.clip.modeling_clip import CLIPModel
from diffusers import WanImageToVideoPipeline, WanTransformer3DModel
print("Wan/Transformers import smoke test passed")
PY

ENV PYTHONPATH=/opt/wan-studio
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
