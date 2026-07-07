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

The worker registry defines future workers/addons/plugins without running them. Initial workers include Knowledge Graph, Creative Studio, Image Worker, Workflow Manager, Model Registry, ComfyUI health client, UnityStitches, Printify, Etsy, phone ingestion, and briefing workers.

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
- Workflow Manager lists and selects configured workflow placeholders
- Image Worker creates safe plans with `execution_enabled: false`
- ComfyUI client checks `/system_stats` only

No ComfyUI workflow execution, Printify call, Etsy call, upload, publish, order, or send operation is implemented.

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

## UnityStitches Product Pipeline

UnityStitches is the draft-only product pipeline for inclusive Etsy/Printify product ideas. It generates local product draft packages and creates a Creative Studio pipeline job for the daily run.

Each run generates exactly two local drafts: one women's underwear product and one rotating configured product. Drafts include product concepts, niches, prompts, titles, tags, descriptions, pricing notes, blueprint search notes, and `needs_review` status.

API routes:

- `GET /unitystitches/health`
- `POST /unitystitches/generate-daily-drafts`
- `GET /unitystitches/drafts`
- `GET /unitystitches/drafts/{date}`

Every UnityStitches step remains draft-only and approval-gated.

## Local ComfyUI

ComfyUI is the planned local image engine, running on James's desktop GPU target: GTX 1080 Ti. JamesOS owns the workflow, storage, safety model, and approvals; ComfyUI only renders images after an approved local workflow requests it.

ComfyUI readiness is implemented for health and planning only. No workflow execution is implemented.

## Printify And Etsy

Printify is the planned product draft target. Etsy is the planned sales platform. Both remain future integrations.

Current rules:

- Do not call Printify yet.
- Do not call Etsy yet.
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
