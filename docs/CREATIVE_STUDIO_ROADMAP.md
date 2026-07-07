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
- Control Center admin/readiness foundation
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
  - `creative_pipeline`
  - `creative_image_generation`
  - `creative_product_draft`
  - `creative_mockup`
  - `creative_social_post`
- queue-backed pipeline shell:
  - `idea`
  - `prompt`
  - `image`
  - `mockup`
  - `listing`
  - `review`
  - `printify_draft`
  - `etsy_review`
  - `complete`

Still not included:

- ComfyUI execution
- Printify calls
- Etsy calls
- product publishing
- orders
- sending

## Phase 3: Creative Studio Review Shell

Planned:

- Control Center-backed health and approval summary in Jade
- dashboard for creative jobs
- draft package viewer
- approve/reject/regenerate actions
- source and evidence labels
- local asset browser
- clear safety state for every draft

The review shell should be powered by Job Queue jobs and local draft files.

## Phase 4: UnityStitches Product Pipeline

Status: foundation in place.

- daily product draft packages
- configurable product mix
- niche rotation
- Etsy title, tags, and descriptions
- pricing notes
- Printify blueprint search notes
- `needs_review` status
- `approval_required: true`
- Creative Studio pipeline job per run
- exactly two drafts per run:
  - one women's underwear product
  - one rotating configured product
- Creative Intelligence compatibility checks before package creation
- hard block on teacher/school/child-related underwear or intimate-apparel pairings

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

Product compatibility boundary:

- women's underwear may only use underwear-safe niches such as pride, self-love, confidence, body positivity, mental health positivity, Thai/English identity, pronouns/names, seasonal inclusive, and clean adult partner humor
- teacher, school, education, classroom, student, kids, special education, speech therapy, occupational therapy, back-to-school, and child-related niches may only use non-intimate products such as shirts, sweatshirts, hoodies, totes, mugs, stickers, classroom accessories, and seasonal gifts

Everything remains draft-only. ComfyUI, Printify, Etsy, publishing, ordering, and sending remain disabled.

## Phase 5: Local ComfyUI Image Generation

Status: approved single-image local generation is available for explicitly approved image jobs.

Active readiness pieces:

- ComfyUI health check against `http://127.0.0.1:8188/system_stats`
- Model Registry at `~/JamesOSData/JamesOS/AI/model_registry.yaml`
- Workflow Manager for listing, selection, and path validation
- Image Worker safe execution plans
- approved single-image execution through local ComfyUI only
- generated draft assets saved under `~/JamesOSData/JamesOS/CreativeStudio/Generated/YYYY-MM-DD/<job_id>/`
- one image job at a time
- global execution remains disabled unless an approved job is actively executing

Implemented execution:

- local ComfyUI API on the desktop
- GTX 1080 Ti-aware workflow choices
- workflow JSON loading
- placeholder replacement for prompt/negative prompt/checkpoint/seed/size
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

Status: read-only Etsy performance-history foundation added; live sync remains placeholder until OAuth/shop credentials are configured and the connector is intentionally activated.

Planned/active:

- niche performance notes
- seasonal timing
- pricing suggestions
- listing quality checks
- draft iteration recommendations
- evidence-backed creative direction
- read-only UnityStitches Etsy performance tables
- local performance scoring influence when history exists

Sales intelligence should advise first, create queued draft tasks second, and act externally only after approval.

Read-only Etsy safety:

- no listing creation or edits
- no publishing, renewal, deactivation, or deletion
- no messages
- no order fulfillment
- no Printify calls
- no ComfyUI calls
- no image uploads

## Safety Model

Creative Studio must keep these defaults:

- approval-first
- local-first
- draft-only
- evidence-labeled when possible
- Job Queue-backed for consequential actions
- no Printify/Etsy/ComfyUI execution until the corresponding phase is intentionally implemented
