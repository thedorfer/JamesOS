# Image Worker

The Image Worker prepares safe image-generation plans and can execute exactly one approved local ComfyUI image job at a time.

Default product artwork now means flat printable design artwork, not lifestyle photography or a mockup.

Current responsibilities:

- accept a Creative Package or Prompt Package
- select a workflow from the Workflow Manager
- select a compatible model from the Model Registry
- select a prompt template from Prompt Library
- select a style from Style Registry
- include brand ID/name/voice from Brand Registry
- suggest local asset metadata from Asset Library
- prefer structured `creative_spec` input and convert it to a prompt package
- prefer `design_recipe` inside `creative_spec` when present
- return a reviewable image-generation plan
- execute only approved `image_generation` or `creative_image_generation` jobs
- reselect an executable ComfyUI API prompt template from Workflow Manager at execution time
- save generated draft assets locally under JamesOSData
- target standalone, centered, POD-safe print graphics by default
- track `design_artifact` metadata for print-ready PNG candidates

Current safety fields:

```text
execution_enabled: false
requires_approval: true
comfyui_execution_enabled: false
printify_execution_enabled: false
etsy_execution_enabled: false
publishing_enabled: false
upload_enabled: false
send_enabled: false
```

API routes:

```text
GET /image-worker/health
POST /image-worker/plan
POST /image-worker/create-test-job
POST /image-worker/jobs/{job_id}/execute-approved
GET /image-worker/jobs/{job_id}/prepared-workflow
GET /image-worker/jobs/{job_id}/comfy-response
GET /comfyui/health
```

Execution rules:

- job must already exist
- job must be explicitly approved
- only one image job may run at a time
- ComfyUI URL must be local: `http://127.0.0.1:8188`
- the ComfyUI browser's currently open workflow is ignored
- workflow execution uses API prompt templates from disk
- workflow JSON and checkpoint must exist
- workflows may use placeholders for positive prompt, negative prompt, checkpoint name, seed, width, height, and filename prefix
- a prepared copy is saved as `prepared_workflow.json` beside the generated PNG
- ComfyUI non-200 response bodies are saved as `comfy_response.json` beside `prepared_workflow.json`
- outputs are saved locally only
- transparent print design jobs are prompt-only transparent candidates until local background removal exists
- Printify, InkedJoy, Etsy, upload, publish, order, listing creation, and send behavior remain disabled

Provider status language:

- local generated design status remains `ready_for_pod_review`
- `provider_status` may be `manual_upload_ready` or `provider_review_ready`
- `ready_for_printify_review` is only used when the selected provider is actually Printify
- there is no `ready_for_inkedjoy_review` status

Flat design rules for `design_art` / `print_design_basic`:

- no human model
- no person wearing product
- no room/lifestyle background
- no product photo
- no mannequin, face, hands, body, or portrait
- centered composition
- white or transparent-background-friendly background
- high contrast and large readable text
- mockup language is only appropriate when the stage is explicitly `mockup`

Workflow selection exposes:

- `requested_workflow_type`
- `selected_workflow_type`
- `workflow_alias_used`

If `print_design_basic` is requested but only `product_art_basic` exists, JamesOS may use `product_art_basic` as a compatibility alias and sets `workflow_alias_used: true`.

Structured execution errors are returned as:

```json
{
  "status": "error",
  "error_code": "workflow_is_comfyui_ui_format_export_api_needed",
  "message": "Workflow file appears to be a ComfyUI UI workflow export, not an API prompt.",
  "job_id": "JOB_ID",
  "workflow_path": "/path/to/workflow.json",
  "next_step": "In ComfyUI, save/export the API prompt JSON format for JamesOS execution."
}
```

Recognized error codes include `no_executable_workflow_template`, `workflow_file_not_json`, `workflow_is_comfyui_ui_format_export_api_needed`, `workflow_is_jamesos_spec_not_comfyui_api_prompt`, `workflow_missing_required_nodes`, `workflow_placeholder_not_replaced`, `workflow_model_checkpoint_missing`, `comfyui_not_running`, `comfyui_rejected_prompt`, `comfyui_output_missing`, and `image_generation_timeout`.

Timeout debugging:

- confirm ComfyUI is running at `http://127.0.0.1:8188`
- inspect the saved `prepared_workflow.json`
- inspect saved `comfy_response.json` when ComfyUI rejects a prompt or image download
- check ComfyUI history/logs for rejected node inputs
- lower width, height, or sampler steps for the GTX 1080 Ti

Offline workflow validation:

```bash
python3 scripts/validate_workflow.py workflow.json
```

The validator checks ComfyUI API prompt shape without contacting ComfyUI: every node must have `class_type`, `inputs`, and valid node references.

Realistic Vision may still drift toward photo/person outputs. The default prompt and negative prompt push toward standalone flat vector-style print artwork, but a vector/design checkpoint may be needed for better reliability.

## Design Artifact

Production image jobs include:

```yaml
design_artifact:
  artifact_type: print_ready_png
  background: transparent
  target_width: 4500
  target_height: 5400
  source_generation_width: 1024
  source_generation_height: 1024
  upscale_required: true
  transparent_background_required: true
  transparent_background_requested: true
  transparency_method: prompt_only
  background_removal_required: true
  manual_upload_ready: false
  provider_target: printify
  quality_stage: production_candidate
```

After execution, JamesOS adds `source_image_path`, `output_image_paths`, and `manual_upload_ready: true`, while keeping `final_print_ready: false` when background removal/upscale are still required.

Asset files remain metadata-only. Prompt packages include `asset_prompt_descriptions` such as “six-stripe rainbow pride flag colors” instead of raw filenames.

## Creative Spec

Image jobs may include:

```yaml
creative_spec:
  brand_id:
  brand_name:
  product_type:
  stage:
  niche:
  audience:
  emotional_hook:
  style:
  colors:
  text:
  typography:
  assets:
  layout:
  print_requirements:
  safety_notes:
  design_recipe:
    product_type:
    niche:
    design_goal:
    artwork_type:
    background:
    layout:
    palette:
    text:
    typography:
    motifs:
    assets:
    effects:
    provider:
    print_notes:
```

Prompt Library converts this into positive/negative prompts, image size, recommended workflow type, and recommended model family.

Prompts are now built from `design_recipe` first. `creative_spec` remains business context. Professional prompts are sectioned as `STYLE`, `SUBJECT`, `TYPOGRAPHY`, `LAYOUT`, and `PRINT`; negative terms remain in the negative prompt. Empty sections are omitted.

Design quality levels:

- `draft`: clear concept, simple printable layout
- `production`: clean vector-like artwork, crisp typography, balanced spacing, high contrast, thumbnail readable
- `premium`: vector-like, clean edges, crisp typography, balanced spacing, isolated artwork, transparent background, high contrast, thumbnail optimization

Composition metadata requires centered artwork, about 75% canvas coverage, safe margins, a single focal point, balanced composition, thumbnail readability, clean silhouette, high contrast, large readable typography, and minimal unnecessary detail.

Asset metadata is selected into `selected_assets`. JamesOS scans general Creative Studio assets plus brand assets such as:

```text
~/JamesOSData/JamesOS/Brands/UnityStitches/Assets/
```

Pride/LGBTQ/trans/intersex queries prefer matching flag assets when present. Font files remain metadata-only and do not expose file paths or binary content.

Design runs may create approval-gated `image_generation` jobs for each variation, but they do not auto-execute. Each job still requires explicit approval before local ComfyUI execution.
