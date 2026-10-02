FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    STUDIO_JOB_ROOT=/workspace/studio_jobs \
    WAN_REPO=/opt/Wan2.2

RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg build-essential ninja-build && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/wan-studio
COPY worker ./worker
RUN python -m pip install --upgrade pip wheel setuptools && \
    python -m pip install --no-cache-dir -r worker/requirements.txt

RUN git clone --depth 1 https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2 && \
    grep -v '^flash_attn' /opt/Wan2.2/requirements.txt > /tmp/wan-requirements.txt && \
    python -m pip install --no-cache-dir -r /tmp/wan-requirements.txt && \
    python -m pip install --no-cache-dir -r /opt/Wan2.2/requirements_s2v.txt && \
    python -m pip install --no-cache-dir flash-attn --no-build-isolation

ENV PYTHONPATH=/opt/wan-studio
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "worker.app:app", "--host", "0.0.0.0", "--port", "8000"]
