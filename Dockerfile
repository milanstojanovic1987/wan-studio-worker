FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    HF_HUB_DISABLE_XET=1 \
    HF_XET_HIGH_PERFORMANCE=0 \
    HF_HUB_ETAG_TIMEOUT=60 \
    HF_HUB_DOWNLOAD_TIMEOUT=600 \
    STUDIO_JOB_ROOT=/workspace/studio_jobs \
    WAN_REPO=/opt/Wan2.2 

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg build-essential ninja-build ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# The RunPod base image can contain a FlashAttention extension compiled against
# a different Torch ABI. Remove both package metadata AND stray CUDA .so files.
RUN python -m pip uninstall -y flash-attn flash_attn || true && \
    find /usr/local/lib/python3.11 -depth \
      \( -iname 'flash_attn*' -o -iname 'flash-attn*' -o -iname 'flash_attn_2_cuda*.so' \) \
      -print -exec rm -rf {} + || true

WORKDIR /opt/wan-studio
COPY worker ./worker

RUN python -m pip install --upgrade pip wheel setuptools && \
    python -m pip install --no-cache-dir -r worker/requirements.txt

RUN git clone --depth 1 https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2 && \
    grep -viE '^[[:space:]]*(flash[-_]attn|flash[-_]attention)' /opt/Wan2.2/requirements.txt > /tmp/wan-requirements.txt && \
    grep -viE '^[[:space:]]*(flash[-_]attn|flash[-_]attention)' /opt/Wan2.2/requirements_s2v.txt > /tmp/wan-s2v-requirements.txt && \
    python -m pip install --no-cache-dir -r /tmp/wan-requirements.txt && \
    python -m pip install --no-cache-dir -r /tmp/wan-s2v-requirements.txt

# Purge again in case a transitive dependency left an incompatible binary.
RUN python -m pip uninstall -y flash-attn flash_attn || true && \
    find /usr/local/lib/python3.11 -depth \
      \( -iname 'flash_attn*' -o -iname 'flash-attn*' -o -iname 'flash_attn_2_cuda*.so' \) \
      -print -exec rm -rf {} + || true

# Build must fail here rather than later on a paid GPU if the import is broken.
RUN python - <<'PY'
import glob
bad = []
for pattern in (
    '/usr/local/lib/python3.11/**/flash_attn*',
    '/usr/local/lib/python3.11/**/flash-attn*',
    '/usr/local/lib/python3.11/**/flash_attn_2_cuda*.so',
):
    bad.extend(glob.glob(pattern, recursive=True))
if bad:
    raise RuntimeError('FlashAttention artifacts remain: ' + ', '.join(sorted(set(bad))))

import torch
print('torch', torch.__version__)
from transformers.models.clip.modeling_clip import CLIPModel
from diffusers import WanImageToVideoPipeline, WanTransformer3DModel
print('Wan/Transformers import smoke test passed')
PY

ENV PYTHONPATH=/opt/wan-studio
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
