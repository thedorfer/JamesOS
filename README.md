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
- Supports Android phone ingestion through Tasker.
- Provides a Flutter Jade app for Linux and Android.
- Plans draft-only creative automation for UnityStitches, ComfyUI, Printify, and Etsy.

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

Approval-gated jobs cannot complete unless approved. This model is intended to protect future automations such as product generation, image generation, Printify drafts, Etsy drafts, email actions, and phone-driven workflows.

## Control Center

The Control Center summarizes JamesOS readiness without taking external action:

- API and server config status
- Job Queue counts and approval-needed jobs
- Knowledge Graph and Creative Studio status
- integration readiness for ComfyUI, Printify, Etsy, Tasker/phone ingestion, and Outlook import
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
- `Work`: prioritizes WGL/CGI, tickets, Knowledge Graph, Outlook/email context, reports, and deployments.
- `Private`: uses local context but should not persist chat or write memory notes.

Hidden intent detection still routes local entity, system, memory, family/private, and work questions to the right context sources.

## Creative Roadmap

Jade Creative Studio and UnityStitches are roadmap areas.

Planned future flow:

```text
Reasoner -> Planner -> Job Queue -> Jade Creative Studio pipeline -> UnityStitches draft package -> local ComfyUI image -> Printify draft -> Etsy draft -> James approval
```

Creative Studio now has a queue-backed pipeline shell with these stages:

```text
idea -> prompt -> image -> mockup -> listing -> review -> printify_draft -> etsy_review -> complete
```

The image, Printify, Etsy, publishing, ordering, and sending stages remain disabled placeholders.

Current safety boundaries:

- No Printify execution yet.
- No Etsy execution yet.
- No ComfyUI execution yet.
- No publishing.
- No ordering.
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
python3 scripts/job_queue.py create unitystitches.draft --payload '{"draft_only": true}'
python3 scripts/job_queue.py approve JOB_ID
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
- [Integrations](docs/INTEGRATIONS.md)
- [Control Center](docs/CONTROL_CENTER.md)
- [Planner](docs/PLANNER.md)
- [Workers](docs/WORKERS.md)
- [Knowledge Graph editing roadmap](docs/KNOWLEDGE_GRAPH_EDITING.md)
- [Phone ingestion via Tasker](docs/PHONE_INGESTION_TASKER.md)
- [Creative Studio roadmap](docs/CREATIVE_STUDIO_ROADMAP.md)
- [API](docs/api.md)
- [CLI](docs/cli.md)

## Current Status

JamesOS is a local-first personal assistant and automation platform in active development. The stable foundation is local ingestion, memory/search, Knowledge Graph retrieval, Jade interaction, Job Queue safety, reports, and docs. The creative commerce system is intentionally draft-only and staged behind future approval-gated jobs.
