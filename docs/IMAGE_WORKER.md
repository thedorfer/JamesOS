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
- return a reviewable image-generation plan
- execute only approved `image_generation` or `creative_image_generation` jobs
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
- workflow JSON and checkpoint must exist
- workflows may use placeholders for positive prompt, negative prompt, checkpoint name, seed, width, and height
- outputs are saved locally only
- Printify, Etsy, upload, publish, order, listing creation, and send behavior remain disabled

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

Structured execution errors are returned as:

```json
{
  "status": "error",
  "error_code": "ui_workflow_not_api_workflow",
  "message": "Workflow file appears to be a ComfyUI UI workflow export, not an API prompt.",
  "next_step": "In ComfyUI, save/export the API prompt JSON format for JamesOS execution."
}
```

Recognized error codes include `invalid_workflow_format`, `ui_workflow_not_api_workflow`, `jamesos_spec_not_comfyui_workflow`, `missing_required_comfyui_nodes`, `unreplaced_placeholders`, `comfyui_rejected_prompt`, and `output_missing`.

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
```

Prompt Library converts this into positive/negative prompts, image size, recommended workflow type, and recommended model family.
