# Workflow Manager

The Workflow Manager selects and validates future ComfyUI workflows without executing them. Phase B adds read-only discovery for local ComfyUI workflow JSON files.

Responsibilities:

- list workflows
- get a workflow by name
- validate whether a configured workflow path exists
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

## Workflow Discovery

Workflow roots:

```text
~/AI/Workflows
~/AI/ComfyUI/user/default/workflows
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

`print_design_basic` is the preferred type for flat POD-ready design artwork. `product_art_basic` remains a compatibility alias for older local workflows.

Each discovered workflow reports name, path, type, status, compatible models, recommended products, transparency/mockup capabilities, `enabled: false`, and `execution_enabled: false`.
