# First Local Image Run

This is the safe path for creating one local flat print design PNG for POD review. It does not call Printify, InkedJoy, or Etsy.

## 1. Put a checkpoint in ComfyUI

Example:

```text
~/AI/ComfyUI/models/checkpoints/realisticVisionV60B1_v60B1VAE.safetensors
```

## 2. Put a workflow in AI workflows

```text
~/AI/Workflows/print_design_basic.json
```

`product_art_basic.json` is still accepted as a compatibility alias.

The workflow may use these placeholders:

```text
{{positive_prompt}}
{{negative_prompt}}
{{checkpoint_name}}
{{seed}}
{{width}}
{{height}}
```

## 3. Scan models and workflows

```bash
curl -H "X-JamesOS-Key: $JAMESOS_API_KEY" http://localhost:8787/models/scan
curl -H "X-JamesOS-Key: $JAMESOS_API_KEY" http://localhost:8787/workflows/scan
```

## 4. Create a test image job

CLI:

```bash
python3 scripts/create_test_image_job.py
```

API:

```bash
curl -X POST -H "X-JamesOS-Key: $JAMESOS_API_KEY" http://localhost:8787/image-worker/create-test-job
```

The job requires approval and does not execute automatically.

The helper creates a `creative_spec` for UnityStitches pride `design_art` and stores a prompt package with positive/negative prompt, size, recommended workflow type, and recommended model family. The generated prompt asks for standalone flat centered print artwork with no person and no mockup. It also prints the next approve and execute commands.

## 5. Approve the job

```bash
python3 scripts/job_queue.py approve JOB_ID
```

## 6. Execute the approved job

```bash
curl -X POST -H "X-JamesOS-Key: $JAMESOS_API_KEY" \
  http://localhost:8787/image-worker/jobs/JOB_ID/execute-approved
```

## 7. Find the output PNG

Generated images are saved locally:

```text
~/JamesOSData/JamesOS/CreativeStudio/Generated/YYYY-MM-DD/JOB_ID/
```

If something fails, common causes are:

- no discovered checkpoint: run `/models/scan`
- no `print_design_basic`/`product_art_basic` workflow: place `~/AI/Workflows/print_design_basic.json` and run `/workflows/scan`
- UI workflow instead of API workflow: export/save the ComfyUI API prompt JSON, not the visual-editor workflow JSON
- JamesOS spec instead of ComfyUI workflow: use a numbered-node ComfyUI API prompt
- unreplaced placeholders: confirm the workflow uses supported placeholders exactly
- ComfyUI not running: check `curl http://127.0.0.1:8188/system_stats`
- workflow output missing: confirm the workflow saves an image output
- model not listed in ComfyUI: confirm the checkpoint file is in ComfyUI's models/checkpoints folder and restart/rescan ComfyUI if needed

Safety boundary:

- one image job at a time
- local ComfyUI only: `http://127.0.0.1:8188`
- no Printify calls
- no InkedJoy calls
- no Etsy calls
- no upload
- no publish
- no order
- no send
