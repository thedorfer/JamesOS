# ComfyUI Setup

ComfyUI is planned as the local image generation engine for JamesOS creative workflows. JamesOS owns the workflow, approval model, prompt records, draft storage, and reporting. ComfyUI should only render images after an approved local job asks it to.

## Current Status

ComfyUI execution is not implemented yet.

Current JamesOS rules:

- Do not call ComfyUI from JamesOS yet.
- Do not generate product artwork automatically yet.
- Do not upload generated artwork to Printify or Etsy yet.
- Route future image generation through the Job Queue and approval flow.

## Target Hardware

Desktop GPU target:

```text
NVIDIA GTX 1080 Ti
```

This GPU can run many Stable Diffusion workflows, but future workflows should be designed with VRAM limits in mind. Prefer practical product-design sizes and upscaling workflows over oversized first-pass generations.

## Planned Local Paths

Future workflows:

```text
~/JamesOSData/JamesOS/AI/ComfyUI/workflows/
```

Future generated assets:

```text
~/JamesOSData/JamesOS/Products/UnityStitches/Assets/
```

Future product draft packages:

```text
~/JamesOSData/JamesOS/Products/UnityStitches/Drafts/
```

## Planned Configuration

ComfyUI settings belong in:

```text
~/JamesOSData/JamesOS/Config/integrations.yaml
```

Expected fields:

```yaml
integrations:
  comfyui:
    enabled: false
    status: planned_local_only
    api_url: http://localhost:8188
    gpu_target: GTX 1080 Ti
    execution_enabled: false
```

## Future Client Responsibilities

The future `jamesos/services/comfyui_client.py` should:

- load workflow JSON
- inject positive prompt
- inject negative prompt
- inject seed
- inject width and height
- submit workflow to local ComfyUI
- poll until complete
- download PNG
- save locally under JamesOSData

## Safety Requirements

Future image jobs must:

- be draft-only
- record prompts and seeds
- save output paths locally
- attach output to a reviewable Job Queue job
- require James approval before any Printify/Etsy action

ComfyUI is only an image engine. It is not the workflow owner and should not decide what gets published.
