# JamesOS Architecture

JamesOS is a local-first personal operating system. It combines evidence ingestion, Knowledge Graph and Working Memory, Jade reasoning, a Flutter client, a Job Queue, and approval-first automation.

## Storage Model

JamesOS keeps human-authored notes and machine-owned data separate:

- Human notes: `~/Notes`
- Machine-owned data: `~/JamesOSData`

Generated reports, queues, imports, indexes, product drafts, attachment manifests, and service config belong under `~/JamesOSData`.

## Evidence To Knowledge Graph To Reasoner

The core reasoning and automation pipeline is:

```text
Evidence -> indexes/reports/timeline -> Knowledge Graph / Working Memory -> Reasoner -> Planner -> Creative Intelligence -> Creative Studio Pipeline -> Workers / Image Worker
```

Evidence sources include:

- Obsidian/manual notes
- imported ChatGPT history
- Outlook/Gmail/email archives
- calendar imports
- phone events from Tasker
- attachments and processed files
- reports and timelines
- future product draft packages

The Knowledge Graph and Working Memory layers turn raw evidence into local entities such as people, projects, tickets, topics, files, and decisions. The Reasoner chooses from those local sources before Jade answers. If Jade claims a local fact, it should be grounded in this evidence path.

The Planner is separate from the Reasoner. It proposes next steps and recommended jobs, but does not create or execute jobs. The Job Queue remains the approval boundary.

## Backend

The Python backend provides:

- FastAPI API routes for Jade and integrations
- ingestion and import services
- search and typed indexes
- Knowledge Graph and memory services
- Job Queue operations
- Planner operations
- Brand Registry operations for shop-specific creative rules
- worker registry/readiness operations
- reports and health/config pages

The API is usually served by `scripts/api_server.py` on port `8787`.

## Jade Client

`apps/jade_app/` is the Flutter Jade client. Jade is the user-facing assistant and should stay concise, useful, and evidence-aware. Current visible modes are Chat, Work, and Private. Hidden intent/context detection still routes local entity questions to the right evidence sources.

## Job Queue Backbone

The Job Queue is the automation backbone. It stores durable JSON jobs under:

- `~/JamesOSData/JamesOS/Queue/pending`
- `~/JamesOSData/JamesOS/Queue/in_progress`
- `~/JamesOSData/JamesOS/Queue/processed`
- `~/JamesOSData/JamesOS/Queue/failed`

Each job records:

- `job_id`
- `type`
- `status`
- `created_at`
- `updated_at`
- `priority`
- `requires_approval`
- `approved`
- `payload`
- `steps`
- `logs`

Approval-gated jobs cannot move to `processed` unless approved. Future creative, product, publishing, email, and image tasks should flow through this queue.

## Planner

The Planner converts user intent into proposed, approval-first plans. It supports initial intents for daily product generation, creative image generation, Knowledge Graph rebuilds, briefing generation, and phone ingestion review.

Planner output includes recommended jobs and next actions. It does not execute those recommendations or write to the Job Queue.

API routes:

- `GET /planner/health`
- `POST /planner/plan`

## Worker Registry

The worker registry defines future workers/addons/plugins without running them. Initial workers include Knowledge Graph, Creative Studio, Image Worker, Workflow Manager, Model Registry, ComfyUI health client, brand product pipelines, POD provider review, Etsy, phone ingestion, and briefing workers.

API routes:

- `GET /workers`
- `GET /workers/{worker_name}`

All worker execution flags are false in this phase.

## Image Readiness

The future image path is:

```text
Planner -> Creative Intelligence -> Creative Studio Pipeline -> Image Worker -> ComfyUI
```

Current implementation is readiness-only:

- Model Registry creates `~/JamesOSData/JamesOS/AI/model_registry.yaml`
- Workflow Manager discovers local workflow JSON files and writes `~/JamesOSData/JamesOS/AI/workflow_inventory.json`
- Workflow Manager lists, validates, classifies, and selects workflows without executing them
- Image Worker creates safe plans with `execution_enabled: false`
- ComfyUI client checks `/system_stats` only

No ComfyUI workflow execution, Printify call, Etsy call, upload, publish, order, or send operation is implemented.

## Brand Registry

Brand Registry centralizes brand/shop rules so Creative Intelligence, Image Worker, and future POD/Etsy workers do not hardcode shop assumptions. It stores brand voice, allowed/blocked niches, allowed/blocked products, blocked product/niche pairs, preferred product mix, design preferences, SEO preferences, pricing/mockup preferences, trademark notes, approval rules, and integration safety flags.

Brands are configured through the local brand registry. External writes remain disabled by default.

## Creative Foundations

Prompt Library, Asset Library, and Style Registry provide brand-aware planning inputs for Image Worker. They store prompt templates, style definitions, and asset metadata under JamesOSData. They do not expose font files, execute ComfyUI, generate images, call shops, upload, publish, order, or send anything.

## Server Configuration And Health

Server and integration configuration lives under:

- `~/JamesOSData/JamesOS/Config/server.yaml`
- `~/JamesOSData/JamesOS/Config/integrations.yaml`

The health/config foundation reports local paths, enabled integration settings, and safety flags. It does not call external APIs.

API routes:

- `GET /server/config`
- `GET /server/health`
- `GET /server/page`

The generated page is:

```text
~/JamesOSData/JamesOS/Reports/Server Configuration.md
```

## Control Center

The Control Center is the admin/readiness layer over the current pipeline. It summarizes API health, Job Queue counts, approval-needed jobs, Knowledge Graph status, Creative Studio status, server config status, integration readiness, and important JamesOSData storage paths.

API routes:

- `GET /control-center`
- `GET /control-center/health`
- `GET /control-center/services`
- `GET /control-center/integrations`
- `GET /control-center/jobs`
- `GET /control-center/storage`
- `GET /control-center/summary`

The generated report is:

```text
~/JamesOSData/JamesOS/Reports/Control Center.md
```

Control Center is observational. It does not execute ComfyUI, call Printify, call Etsy, publish, order, or send anything.

## Jade Creative Studio

Jade Creative Studio is the planned creative automation workspace. It will use the Job Queue to prepare, review, approve, regenerate, and archive draft creative work.

The current foundation supports approval-gated placeholder creative jobs, health reporting, and a queue-backed pipeline shell.

Pipeline stages:

```text
idea -> prompt -> image -> mockup -> listing -> review -> printify_draft -> etsy_review -> complete
```

The image, mockup, Printify, Etsy, publishing, ordering, and sending stages remain disabled placeholders.

API routes:

- `GET /creative-studio/pipelines`
- `GET /creative-studio/pipelines/{job_id}`
- `POST /creative-studio/pipelines`

## Brand Product Pipelines

JamesOS can host brand-specific draft-only product pipelines for Etsy/POD product ideas. These pipelines generate local product draft packages and create Creative Studio pipeline jobs for review.

Drafts include product concepts, niches, prompts, titles, tags, descriptions, pricing notes, provider review notes, and `needs_review` status.

Every brand pipeline step remains draft-only and approval-gated.

## Local ComfyUI

ComfyUI is the planned local image engine, running on James's desktop GPU target: GTX 1080 Ti. JamesOS owns the workflow, storage, safety model, and approvals; ComfyUI only renders images after an approved local workflow requests it.

ComfyUI readiness is implemented for health and planning only. No workflow execution is implemented.

## Printify And Etsy

POD providers are planned product review targets. Etsy is the planned read-only sales-learning source and future review target. All write operations remain future integrations.

Current rules:

- Do not call Printify yet.
- Do not call Etsy write APIs.
- Do not publish.
- Do not order.
- Do not send to production.
- Do not create live listings.
- Always require James approval before publication or production.

## Approval-First Safety Model

JamesOS should create reviewable local drafts and queued jobs first. It should act externally only after explicit approval. This applies to product automation, image generation, email, publishing, ordering, and future sales operations.

## Personal Wiki And Knowledge Graph Editing

Knowledge Graph editing is roadmap-only. The current API can report future edit capabilities, but editing is disabled.

Planned capabilities include edit summary, add fact, mark fact wrong, merge entity, refresh from evidence, source citations, and confidence levels.
