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
- outputs are saved locally only
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
- check ComfyUI history/logs for rejected node inputs
- lower width, height, or sampler steps for the GTX 1080 Ti

Realistic Vision may still drift toward photo/person outputs. The default prompt and negative prompt push toward standalone flat vector-style print artwork, but a vector/design checkpoint may be needed for better reliability.

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

Asset metadata is selected into `selected_assets`. JamesOS scans general Creative Studio assets plus brand assets such as:

```text
~/JamesOSData/JamesOS/Brands/UnityStitches/Assets/
```

Pride/LGBTQ/trans/intersex queries prefer matching flag assets when present. Font files remain metadata-only and do not expose file paths or binary content.
