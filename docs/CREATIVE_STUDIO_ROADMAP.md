# Jade Creative Studio Roadmap

This roadmap describes the intended direction without implementing later phases in Phase 1.

## Phase 1: Job Queue Foundation

Status: implemented.

- Durable JSON jobs.
- Pending, in-progress, processed, and failed storage.
- API and CLI controls.
- Approval gates.
- Job Queue report.

Phase 1 does not generate products, images, Printify drafts, Etsy drafts, orders, or live listings.

## Phase 2: Creative Studio Shell

Planned:

- Review dashboard for creative jobs.
- Draft package viewer.
- Approval and rejection flows.
- Regeneration requests.
- Evidence and source labels attached to creative decisions.

## Phase 3: UnityStitches Draft Pipeline

Planned:

- Daily draft product packages.
- Configurable product mix.
- Niche rotation.
- Etsy title, tags, and description drafts.
- Pricing and Printify blueprint notes.
- Status: `needs_review`.

Every generated product remains draft-only until James approves it.

## Phase 4: Local ComfyUI Image Generation

Planned:

- Load approved ComfyUI workflow JSON.
- Inject prompts, negative prompts, seeds, and dimensions.
- Submit to local ComfyUI.
- Save generated assets under JamesOSData.
- Attach image paths to draft product jobs.

ComfyUI is only the image engine. JamesOS owns the workflow, approval, storage, and reporting.

## Phase 5: Printify Draft Integration

Planned placeholders:

- List shops.
- List blueprints.
- Find product blueprint.
- Upload artwork.
- Create product draft.

Printify remains a publishing target only. No production order, live publish, or send action can happen without approval.

## Phase 6: Etsy Draft Integration

Planned:

- Prepare Etsy draft listing metadata.
- Connect approved Printify draft details.
- Track listing readiness.

No live Etsy listing is created in Phase 1, and future listing publication must require James approval.

## Phase 7: Sales Intelligence

Planned:

- Seasonal product timing.
- Niche performance notes.
- Draft quality scoring.
- Pricing suggestions.
- Review of what is selling, stale, or worth iterating.

Sales intelligence should advise first, queue jobs second, and act only after approval.

## Approval-First Rule

The Creative Studio is not an autopublisher. It should create reviewable work packages and route every consequential action through the Job Queue approval model.
