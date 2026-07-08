# Workflow Manager

The Workflow Manager selects and validates ComfyUI workflow templates without executing them. JamesOS-owned API prompt templates on disk are the execution source of truth.

Responsibilities:

- list workflows
- get a workflow by name
- validate whether a configured workflow path exists
- classify workflow format as `comfyui_api_prompt`, `comfyui_ui_workflow`, `jamesos_spec`, or `unknown`
- create the managed default `print_design_basic.api.json`
- select executable API prompt templates
- choose a workflow for a creative package
- scan local workflow folders
- write a local workflow inventory and report
- return `execution_enabled: false`

It does not submit prompts, queue ComfyUI jobs, upload images, or publish anything.

API routes:

```text
GET /workflows
GET /workflows/scan
GET /workflows/{workflow_name}
```

## Managed Template

Default template:

```text
~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates/print_design_basic.api.json
~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates/transparent_print_design_basic.api.json
```

This is a ComfyUI API prompt, not the visual UI workflow export. It uses only built-in nodes: `CheckpointLoaderSimple`, two `CLIPTextEncode` nodes, `EmptyLatentImage`, `KSampler`, `VAEDecode`, and `SaveImage`.

`transparent_print_design_basic.api.json` uses the same core nodes. It requests transparency through prompt wording only and is marked `background_removal_required: true`.

To reset it:

```bash
rm ~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates/print_design_basic.api.json
python3 - <<'PY'
from jamesos.services import workflow_manager
print(workflow_manager.initialize_default_workflow_templates())
PY
```

## Workflow Discovery

Workflow roots:

```text
~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates
~/AI/Workflows
~/JamesOSData/JamesOS/AI/Workflows
```

Supported extension:

```text
.json
```

Inventory:

```text
~/JamesOSData/JamesOS/AI/workflow_inventory.json
```

Report:

```text
~/JamesOSData/JamesOS/Reports/Workflow Registry.md
```

Recognized workflow types:

- `print_design_basic`
- `transparent_print_design_basic`
- `product_art`
- `transparent_png`
- `typography`
- `mockup`
- `listing_image`
- `social_post`
- `background_removal`
- `upscale`
- `img2img`
- `generic`

`print_design_basic` is the preferred type for flat POD-ready design artwork. `product_art_basic` remains a compatibility alias only when it is a valid ComfyUI API prompt.

`transparent_print_design_basic` is the preferred type for production-candidate manual-upload PNGs.

Each discovered workflow reports name, path, type, workflow format, API prompt validity, status, compatible models, recommended products, transparency/mockup capabilities, `enabled: false`, and `execution_enabled: false`.

The ComfyUI browser's open workflow is never inspected or used by JamesOS.

Model Registry note: common SD1.5 checkpoint names such as DreamShaper, RealisticVision, Deliberate, Counterfeit, Anything/AnythingV5, EpicRealism, RevAnimated, MajicMix, and AbsoluteReality classify as `sd15` when found under checkpoint folders. VAE filename text does not override checkpoint-folder classification.
