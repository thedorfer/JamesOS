# JamesOS

JamesOS is a local-first personal operating system and assistant layer built for James. It combines a Python/FastAPI backend, local evidence ingestion, a Knowledge Graph and Working Memory layer, a Flutter client named Jade, and an approval-first automation backbone.

The project is intentionally personal and safety-oriented. JamesOS can collect and reason over local notes, imported ChatGPT history, work emails, phone events, reports, tickets, and future creative-product drafts, but consequential automation must pass through explicit review and approval.

## What JamesOS Does

- Runs a local FastAPI API for Jade and integrations.
- Keeps human notes in `~/Notes`.
- Keeps machine-owned data in `~/JamesOSData`.
- Builds local evidence into search indexes, reports, timelines, Working Memory, and Knowledge Graph pages.
- Lets Jade answer from local context instead of guessing.
- Uses Planner to turn intent into proposed work without executing it.
- Provides a Job Queue for approval-first automation.
- Registers future workers/addons through a non-executing worker registry.
- Provides a Control Center API/report for health, integrations, jobs, storage, and automation readiness.
- Supports Android phone ingestion through Tasker or desktop/laptop pull alternatives.
- Provides a Flutter Jade app for Linux and Android.
- Supports draft-only multi-brand POD and creative automation across local image generation, provider review, and Etsy sales intelligence.
- Provides a read-only Etsy sales-history foundation for provider-agnostic creative learning.
- Provides ComfyUI readiness, Model Registry, Workflow Manager, and Image Worker planning/execution foundations with local execution approval-gated.
- Provides a Brand Registry and POD Provider Registry so creative/product/provider rules can support multiple shops safely.
- Provides recipe-driven Design Runs, Design Planner, and Design Critic foundations for consistent commercial design generation.

## Core Architecture

The central flow is:

```text
Evidence -> Knowledge Graph / Working Memory -> Reasoner -> Jade UI / API
```

Evidence includes notes, imported ChatGPT exports, Outlook/Gmail archives, calendar imports, phone events, reports, timelines, attachments, and product draft packages.

Jade uses this local evidence to answer questions, show clickable Knowledge Graph details, and prepare draft-only automation jobs. The Reasoner should prefer local evidence over memory-like guesswork, especially for people, work tickets, family/private context, and product automation.

## Approval-First Automation

JamesOS is not an autopublisher.

The Job Queue stores durable jobs under:

```text
~/JamesOSData/JamesOS/Queue/pending
~/JamesOSData/JamesOS/Queue/in_progress
~/JamesOSData/JamesOS/Queue/processed
~/JamesOSData/JamesOS/Queue/failed
```

Approval-gated jobs cannot complete unless approved. This model is intended to protect automations such as product generation, image generation, provider drafts, marketplace drafts, email actions, and phone-driven workflows.

## Control Center

The Control Center summarizes JamesOS readiness without taking external action:

- API and server config status
- Job Queue counts and approval-needed jobs
- Knowledge Graph and Creative Studio status
- integration readiness for ComfyUI, POD providers, Etsy, Tasker/phone ingestion, and Outlook import
- storage paths for JamesOSData, Knowledge Graph, Queue, Creative Studio, Reports, Phone, Email, and ChatGPT data

API routes:

```text
GET /control-center
GET /control-center/health
GET /control-center/services
GET /control-center/integrations
GET /control-center/jobs
GET /control-center/storage
GET /control-center/summary
```

The generated report is:

```text
~/JamesOSData/JamesOS/Reports/Control Center.md
```

## Jade Modes

The user-facing Jade modes are intentionally small:

- `Chat`: default, conversational, with automatic local context detection.
- `Work`: prioritizes work context, tickets, Knowledge Graph, email context, reports, and deployments.
- `Private`: uses local context but should not persist chat or write memory notes.

Hidden intent detection still routes local entity, system, memory, family/private, and work questions to the right context sources.

## Creative Studio Roadmap

Jade Creative Studio is an approval-first foundation for multi-brand POD and creative automation.

Current flow:

```text
Reasoner / Planner -> Job Queue -> Recipe Library -> Design Planner -> Prompt Package -> Image Worker -> ComfyUI -> Design Critic -> Print Readiness -> POD review
```

The Creative Studio pipeline stages are designed around:

```text
idea -> recipe -> design_plan -> prompt -> image -> critique -> print_readiness -> review -> provider_review -> marketplace_review -> complete
```

The image stage can execute one approved local ComfyUI job and save a local PNG. InkedJoy, Printify, Etsy, publishing, uploads, ordering, and sending remain disabled.

The Creative Studio direction is:

- multi-brand POD and creative automation
- brand registry and provider registry
- recipe-driven design generation
- design planning and critique
- approval-first local automation

ComfyUI readiness routes are available for local planning, health, and approval-gated image generation:

```text
GET /models
GET /models/scan
GET /models/{model_name}
GET /workflows
GET /workflows/scan
GET /workflows/{workflow_name}
GET /image-worker/health
POST /image-worker/plan
POST /image-worker/create-test-job
POST /image-worker/jobs/{job_id}/execute-approved
GET /image-worker/jobs/{job_id}/prepared-workflow
GET /image-worker/jobs/{job_id}/comfy-response
GET /comfyui/health
```

Brand Registry routes:

```text
GET /brands
GET /brands/health
GET /brands/default
GET /brands/{brand_id}
POST /brands/{brand_id}/validate
```

POD Provider Registry routes:

```text
GET /pod-providers
GET /pod-providers/health
GET /pod-providers/{provider_id}
```

Creative Foundation routes:

```text
GET /prompts
GET /prompts/{template_name}
GET /assets
GET /styles
GET /styles/{style_name}
GET /recipes
GET /recipes/{recipe_id}
GET /recipes/by-product/{product_type}
GET /design-planner/health
POST /design-planner/plan
GET /design-planner/plans/{plan_id}
GET /design-critic/health
POST /design-critic/critique-plan
POST /design-critic/critique-artifact
GET /design-critic/critiques/{critic_id}
POST /design-runs/create
GET /design-runs
GET /design-runs/{run_id}
POST /design-runs/{run_id}/score
POST /design-runs/{run_id}/promote-best
```

Design runs create four recipe-driven variations, preserve Design DNA, Design Planner output, logical layer manifests, and pre-generation Design Critic output, score print readiness, and promote a single best candidate only when it reaches the `>= 90` threshold and critic review supports promotion. Product-specific recipes can favor typography, motifs, or pattern systems depending on product fit.

The Model Registry scan is read-only. It inventories local files under `~/AI/Models`, `~/AI/ComfyUI/models`, and `~/JamesOSData/JamesOS/AI/Models`, writes `~/JamesOSData/JamesOS/AI/model_inventory.json`, and keeps all discovered models `enabled: false`.

The Workflow Manager scan is also read-only. It inventories workflow JSON files under `~/AI/Workflows`, `~/AI/ComfyUI/user/default/workflows`, and `~/JamesOSData/JamesOS/AI/Workflows`, writes `~/JamesOSData/JamesOS/AI/workflow_inventory.json`, and keeps all discovered workflows `execution_enabled: false`.

Current safety boundaries:

- No unapproved ComfyUI execution; only one approved local image job may run at a time.
- No Printify execution yet.
- No InkedJoy execution yet.
- No Etsy write execution yet. Etsy performance history is read-only and returns `not_configured` until OAuth/shop credentials are supplied outside Git.
- No publishing.
- No ordering.
- No uploading to providers or marketplaces.
- No sending to production.
- No live listings without James approval.

## Repository Shape

```text
jamesos/                 Python backend, services, FastAPI API
scripts/                 CLI helpers and maintenance commands
apps/jade_app/           Flutter Jade client
docs/                    Architecture, setup, integration, and roadmap docs
tests/                   Python regression tests
```

## Common Commands

From repo root:

```bash
python3 -m py_compile jamesos/services/*.py scripts/*.py
python3 -m unittest discover tests
```

Run the API server:

```bash
python3 scripts/api_server.py
curl http://localhost:8787/health
```

Flutter app:

```bash
cd apps/jade_app
flutter analyze
flutter run -d linux
```

Job Queue:

```bash
python3 scripts/job_queue.py list
python3 scripts/job_queue.py create creative.draft --payload '{"draft_only": true}'
python3 scripts/job_queue.py approve JOB_ID
```

Design run example:

```bash
python3 scripts/create_design_run.py \
  --brand default \
  --product womens_underwear \
  --niche "trans pride" \
  --recipe underwear/pride_pattern \
  --variations 4 \
  --quality premium \
  --provider printify
```

Planner and worker readiness:

```text
GET /planner/health
POST /planner/plan
GET /workers
GET /workers/{worker_name}
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Desktop setup](docs/SETUP_DESKTOP.md)
- [ComfyUI setup](docs/COMFYUI_SETUP.md)
- [ComfyUI service](docs/COMFYUI_SERVICE.md)
- [Model Registry](docs/MODEL_REGISTRY.md)
- [Workflow Manager](docs/WORKFLOW_MANAGER.md)
- [Image Worker](docs/IMAGE_WORKER.md)
- [Design Planner](docs/DESIGN_PLANNER.md)
- [Design Critic](docs/DESIGN_CRITIC.md)
- [Design Runs](docs/DESIGN_RUNS.md)
- [Recipe Library](docs/RECIPE_LIBRARY.md)
- [Design DNA](docs/DESIGN_DNA.md)
- [Print Readiness Scoring](docs/PRINT_READINESS_SCORING.md)
- [Print-Ready Design Artifact](docs/PRINT_READY_DESIGN_ARTIFACT.md)
- [Brand Registry](docs/BRAND_REGISTRY.md)
- [POD Provider Registry](docs/POD_PROVIDER_REGISTRY.md)
- [Creative Foundations](docs/CREATIVE_FOUNDATIONS.md)
- [Asset Packs](docs/ASSET_PACKS.md)
- [Integrations](docs/INTEGRATIONS.md)
- [Control Center](docs/CONTROL_CENTER.md)
- [Planner](docs/PLANNER.md)
- [Workers](docs/WORKERS.md)
- [Knowledge Graph editing roadmap](docs/KNOWLEDGE_GRAPH_EDITING.md)
- [Phone ingestion](docs/PHONE_INGESTION.md)
- [Phone ingestion via Tasker](docs/PHONE_INGESTION_TASKER.md)
- [Creative Studio roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)
- [Creative Intelligence](docs/CREATIVE_INTELLIGENCE.md)
- [Etsy read-only performance](docs/ETSY_READONLY_PERFORMANCE.md)
- [API](docs/api.md)
- [CLI](docs/cli.md)

## Current Status

JamesOS is a local-first personal assistant and automation platform in active development. The stable foundation is local ingestion, memory/search, Knowledge Graph retrieval, Jade interaction, Job Queue safety, reports, and docs. The creative commerce system is recipe-driven, approval-first, and local-first; external provider and marketplace actions remain disabled until future explicitly approved phases.
