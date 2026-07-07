# Image Worker

The Image Worker prepares safe image-generation plans and can execute exactly one approved local ComfyUI image job at a time.

Current responsibilities:

- accept a Creative Package or Prompt Package
- select a workflow from the Workflow Manager
- select a compatible model from the Model Registry
- select a prompt template from Prompt Library
- select a style from Style Registry
- include brand ID/name/voice from Brand Registry
- suggest local asset metadata from Asset Library
- return a reviewable image-generation plan
- execute only approved `image_generation` or `creative_image_generation` jobs
- save generated draft assets locally under JamesOSData

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
POST /image-worker/jobs/{job_id}/execute-approved
GET /comfyui/health
```

Execution rules:

- job must already exist
- job must be explicitly approved
- only one image job may run at a time
- ComfyUI URL must be local: `http://127.0.0.1:8188`
- workflow JSON and checkpoint must exist
- outputs are saved locally only
- Printify, Etsy, upload, publish, order, listing creation, and send behavior remain disabled
