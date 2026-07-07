# Jade Creative Studio Roadmap

Jade Creative Studio is the planned creative automation surface for JamesOS. It should create reviewable local work packages, not uncontrolled external actions.

## North Star

```text
Evidence -> Job Queue -> Creative Studio -> Draft package -> James approval -> optional external draft target
```

Creative Studio should support UnityStitches, local image generation, product copy, review workflows, and future sales intelligence while staying approval-first.

## Phase 1: Foundations

Status: foundation in place.

- Job Queue
- approval-gated job model
- server config and integration health foundation
- architecture and roadmap docs
- safe placeholders for Creative Studio, UnityStitches, and ComfyUI

Not included:

- image generation
- Printify calls
- Etsy calls
- product publishing
- orders
- send-to-production actions

## Phase 2: Creative Studio Foundation

Status: foundation in place.

- `jamesos/services/creative_studio.py`
- `scripts/creative_studio.py`
- `~/JamesOSData/JamesOS/Config/creative_studio.yaml`
- `~/JamesOSData/JamesOS/Reports/Creative Studio.md`
- Creative Studio API routes
- Job Queue-backed creative jobs
- safe placeholder job types:
  - `creative_image_generation`
  - `creative_product_draft`
  - `creative_mockup`
  - `creative_social_post`

Still not included:

- ComfyUI execution
- Printify calls
- Etsy calls
- product publishing
- orders
- sending

## Phase 3: Creative Studio Review Shell

Planned:

- dashboard for creative jobs
- draft package viewer
- approve/reject/regenerate actions
- source and evidence labels
- local asset browser
- clear safety state for every draft

The review shell should be powered by Job Queue jobs and local draft files.

## Phase 4: UnityStitches Product Pipeline

Planned:

- daily product draft packages
- configurable product mix
- niche rotation
- Etsy title, tags, and descriptions
- pricing notes
- Printify blueprint search notes
- `needs_review` status
- `approval_required: true`

Target product direction:

- LGBTQ+ pride
- trans pride
- nonbinary pride
- ally/supporter
- inclusive teacher
- self-love/confidence
- mental health positivity
- Thai/English identity
- seasonal and holiday pride
- Pride Month

Everything remains draft-only.

## Phase 5: Local ComfyUI Image Generation

Planned:

- local ComfyUI API on the desktop
- GTX 1080 Ti-aware workflow choices
- workflow JSON loading
- prompt/negative prompt/seed/size injection
- PNG download and local asset storage
- Job Queue attachment of generated assets

ComfyUI is only the image engine. JamesOS remains the workflow owner.

## Phase 6: Printify Draft Integration

Planned placeholders:

- list shops
- list blueprints
- find product blueprint
- upload artwork
- create product draft

Rules:

- draft-only
- no publishing
- no ordering
- no send to production
- require James approval

## Phase 7: Etsy Draft Integration

Planned:

- prepare Etsy draft metadata
- title/tag/description review
- connect approved product draft details
- track listing readiness

Rules:

- no live listings without approval
- no hidden publishing
- no automatic renewal or sales action without explicit future approval controls

## Phase 8: Sales Intelligence

Planned:

- niche performance notes
- seasonal timing
- pricing suggestions
- listing quality checks
- draft iteration recommendations
- evidence-backed creative direction

Sales intelligence should advise first, create queued draft tasks second, and act externally only after approval.

## Safety Model

Creative Studio must keep these defaults:

- approval-first
- local-first
- draft-only
- evidence-labeled when possible
- Job Queue-backed for consequential actions
- no Printify/Etsy/ComfyUI execution until the corresponding phase is intentionally implemented
