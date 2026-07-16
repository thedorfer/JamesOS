# First Local Image Run

This is the safe path for creating one local flat print design PNG for POD review. It does not call Printify, InkedJoy, or Etsy.

## 1. Put a checkpoint in ComfyUI

Example:

```text
~/AI/ComfyUI/models/checkpoints/realisticVisionV60B1_v60B1VAE.safetensors
```

## 2. Use the JamesOS API workflow template

```text
~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates/print_design_basic.api.json
~/JamesOSData/JamesOS/CreativeStudio/WorkflowTemplates/transparent_print_design_basic.api.json
```

JamesOS creates this managed ComfyUI API prompt template automatically. It does not use the workflow currently open in the ComfyUI browser UI.

To reset/recreate it, delete only that managed template file and run:

```bash
python3 - <<'PY'
from jamesos.services import workflow_manager
print(workflow_manager.initialize_default_workflow_templates())
PY
```

`product_art_basic.json` is only a compatibility fallback if it is a valid ComfyUI API prompt.

For the production-candidate milestone, JamesOS uses `transparent_print_design_basic.api.json`. It requests a transparent background through the prompt only, so the artifact is marked `background_removal_required: true` until a future local background-removal workflow exists.

The workflow may use these placeholders:

```text
{{positive_prompt}}
{{negative_prompt}}
{{checkpoint_name}}
{{seed}}
{{width}}
{{height}}
{{filename_prefix}}
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

Default helper options are:

```text
--quality production --transparent --provider printify
```

API:

```bash
curl -X POST -H "X-JamesOS-Key: $JAMESOS_API_KEY" http://localhost:8787/image-worker/create-test-job
```

The job requires approval and does not execute automatically.

The helper creates a `creative_spec` with a `design_recipe` for Commerce Shop pride `design_art` and stores a prompt package with positive/negative prompt, size, recommended workflow type, and recommended model family. The generated prompt asks for standalone flat centered vector-style print artwork with no person, no product mockup, and no lifestyle background.

The prompt is built from the design recipe first and uses professional sections: `STYLE`, `SUBJECT`, `TYPOGRAPHY`, `LAYOUT`, and `PRINT`.

The helper output also shows:

- workflow template used
- `ComfyUI open workflow is ignored.`
- whether the output is `final_print_ready`, `production_candidate`, or `background_removal_required`
- selected provider
- selected asset metadata
- exact approve CLI/API commands
- exact execute-approved curl command
- command to open the output folder

## 5. Approve the job

```bash
python3 scripts/job_queue.py approve JOB_ID
```

or:

```bash
curl -X POST -H "X-JamesOS-Key: $JAMESOS_API_KEY" \
  http://localhost:8787/jobs/JOB_ID/approve
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
- no `print_design_basic` workflow: recreate the managed `print_design_basic.api.json` template and run `/workflows/scan`
- no executable template: recreate `print_design_basic.api.json`
- UI workflow instead of API workflow: export/save the ComfyUI API prompt JSON, not the visual-editor workflow JSON
- JamesOS spec instead of ComfyUI workflow: use a numbered-node ComfyUI API prompt
- unreplaced placeholders: confirm the workflow uses supported placeholders exactly
- ComfyUI not running: check `curl http://127.0.0.1:8188/system_stats`
- workflow output missing: confirm the workflow saves an image output
- model not listed in ComfyUI: confirm the checkpoint file is in ComfyUI's models/checkpoints folder and restart/rescan ComfyUI if needed
- timeout: check ComfyUI logs/history, lower image size or steps, then retry the approved job

Realistic Vision is photo/person-biased. The default prompt strongly asks for flat vector-style print artwork with no people, rooms, mockups, or worn clothing, but a vector/design-focused checkpoint may still be needed later for more reliable print-design output.

The target print artifact is `4500x5400`, but the first source generation is usually `1024x1024` on the GTX 1080 Ti. JamesOS marks `upscale_required: true` when the output is still a production candidate.

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
