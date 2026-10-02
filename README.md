# Wan Studio — simple RunPod desktop controller

This is the simplified replacement for the earlier multi-model Gradio project.

## What the desktop app does

- Native Windows GUI (PySide6), no browser UI.
- Prepare multiple scenes while RunPod is off.
- Each scene has: starting picture, motion prompt, optional dialogue, optional recorded audio, and TTS voice.
- Silent scenes use **Wan 2.2 Lightning I2V**.
- Dialogue/audio scenes use **Wan 2.2 S2V** so speech drives the generated video/lip motion.
- **Generate All** creates one temporary RunPod Pod, processes the batch, downloads every MP4 locally, then terminates the Pod.
- The RunPod request uses ephemeral container disk and sends no persistent/network storage mount.
- The worker exits itself after an idle safety timeout as a second protection against accidental GPU billing if the desktop app disappears.

## Important verification status

The local project logic and mocked lifecycle tests pass. A real paid GPU generation has **not yet been run from this package**, so model/GPU/runtime compatibility still needs one live test before calling the pipeline verified.

## Windows install

1. Install 64-bit Python 3.12.
2. Extract this folder.
3. Double-click `install_windows.bat` once.
4. Double-click `launch_windows.bat`.

Your RunPod API key is entered into the app and is **not saved by this version**.

## One-time worker image build — no local Docker required

The desktop app needs a published worker image. This repository includes `.github/workflows/build-worker.yml` so GitHub can build and publish it to GHCR for you.

1. Put this folder in a GitHub repository.
2. Push to `main` or manually run **Build Wan Studio worker** in GitHub Actions.
3. The image is `ghcr.io/milanstojanovic1987/wan-studio-worker:latest`.
4. Make the GHCR package public (or configure RunPod registry credentials for a private image).
5. Wan Studio → **Settings** defaults to this published worker image.

No Docker installation on the Windows PC is required.

## RunPod behavior

The app uses RunPod REST API v2. It creates a Pod from the worker image with:

- 1 GPU
- 200 GB ephemeral container disk by default
- HTTP port 8000
- no persistent or network mount
- a random per-session worker bearer token

The default GPU is `NVIDIA A100 80GB PCIe` for the first compatibility test. Once the pipeline is verified we can test cheaper 48 GB cards/offload settings.

## Model behavior

### Silent scene

Wan 2.2 Lightning I2V:

- 832×480
- 81 frames
- 16 fps
- official Lightx2v four-step high/low-noise LoRAs

### Dialogue/audio scene

Wan 2.2 S2V:

- starting image + motion prompt + audio
- if you type dialogue and do not supply audio, Kokoro creates the speech audio first
- if you supply recorded audio, it is used directly
- Wan S2V generates the talking video from that audio

Model weights are intentionally **not** baked into the container image. They download to the temporary Pod on first use and disappear when the Pod is terminated.

## Local outputs

Projects default to:

`C:\Users\YOU\WanStudioProjects`

Each project contains `inputs`, `outputs`, and `project.json`.
