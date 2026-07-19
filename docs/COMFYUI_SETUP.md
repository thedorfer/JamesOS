# ComfyUI Setup

Last reviewed: 2026-07-18. ComfyUI and GPU ownership belong to the Linux desktop, never the ThinkBook. General `/app` health treats this as optional/recoverable (normally yellow when absent), and image failure must remain isolated from unrelated workspaces.

ComfyUI is planned as the local image generation engine for JamesOS creative workflows. JamesOS owns the workflow, approval model, prompt records, draft storage, and reporting. ComfyUI should only render images after an approved local job asks it to.

## Current status

This guide originated during the readiness-foundation phase. The current implementation includes approved local generation paths and health integration. Automated local preflight has produced eligible artwork, but the latest browser commerce run produced zero eligible output, so the browser/runtime handoff remains unaccepted. ComfyUI remains a local rendering engine and receives no provider, publication, order, terminal, or privilege authority.
- Do not upload generated artwork to Printify or Etsy yet.
- Route future image generation through the Job Queue and approval flow.

Control Center exposes ComfyUI readiness without execution:

```text
GET /control-center/integrations
GET /comfyui/health
GET /image-worker/health
GET /models/scan
```

Expected safety fields:

```text
configured_api_url: http://127.0.0.1:8188
max_concurrent_image_jobs: 1
one_image_job_at_a_time: true
execution_enabled: false
```

See [ComfyUI service](COMFYUI_SERVICE.md) for localhost service setup.

## Target Hardware

Desktop GPU target:

```text
NVIDIA GTX 1080 Ti
```

This GPU can run many Stable Diffusion workflows, but future workflows should be designed with VRAM limits in mind. Prefer practical product-design sizes and upscaling workflows over oversized first-pass generations.

## Planned Local Paths

Workflow registry:

```text
~/JamesOSData/JamesOS/AI/model_registry.yaml
```

Model inventory scan output:

```text
~/JamesOSData/JamesOS/AI/model_inventory.json
~/JamesOSData/JamesOS/Reports/Model Registry.md
```

The scanner checks local model folders only and keeps every discovered model `enabled: false`.

Future generated assets:

```text
~/JamesOSData/JamesOS/Products/<job-bound-profile>/Assets/
```

Future product draft packages:

```text
~/JamesOSData/JamesOS/Products/<job-bound-profile>/Drafts/
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

The future execution version of `jamesos/services/comfyui_client.py` may:

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
