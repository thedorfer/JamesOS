# Image Worker

The Image Worker prepares safe image-generation plans for future ComfyUI use.

Current responsibilities:

- accept a Creative Package or Prompt Package
- select a workflow from the Workflow Manager
- select a compatible model from the Model Registry
- return a reviewable image-generation plan
- keep execution disabled

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
GET /comfyui/health
```

The Image Worker does not call ComfyUI yet. It only plans.

