# Model Registry

The Model Registry records local model and workflow readiness for future image generation. Phase A adds a read-only scanner so JamesOS can report actual local model readiness.

Config path:

```text
~/JamesOSData/JamesOS/AI/model_registry.yaml
```

Default model placeholders:

- `sdxl_base`
- `sdxl_typography`
- `flux_schnell`
- `flux_dev`
- `transparent_png`
- `mockup_model`

Every model starts with `status: missing` and `enabled: false`.

Default workflow placeholders:

- `product_art`
- `typography_design`
- `transparent_png`
- `mockup`
- `listing_image`

Every workflow starts with `status: missing` and `enabled: false`.

The registry is read by the Workflow Manager and Image Worker. It does not execute models or workflows.

## Phase A Inventory Scan

JamesOS scans these local roots:

```text
~/AI/Models
~/AI/ComfyUI/models
~/JamesOSData/JamesOS/AI/Models
```

Supported categories:

- `checkpoints`
- `loras`
- `vae`
- `embeddings`
- `controlnet`
- `upscalers`
- `clip`
- `unet`
- `diffusion_models`
- `text_encoders`

Supported file extensions:

- `.safetensors`
- `.ckpt`
- `.pt`
- `.pth`
- `.bin`
- `.gguf`

Inventory output:

```text
~/JamesOSData/JamesOS/AI/model_inventory.json
```

Report:

```text
~/JamesOSData/JamesOS/Reports/Model Registry.md
```

Each discovered model reports name, path, category, family, file size, status, `enabled: false`, recommended use, and VRAM notes.

API:

```text
GET /models
GET /models/scan
GET /models/{model_name}
```

The scan reads file names and metadata only. It does not load models, execute ComfyUI, or generate images.
