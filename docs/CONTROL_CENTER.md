# JamesOS Control Center

The Control Center is the server/admin readiness layer for JamesOS. It gathers local health, storage, queue, Knowledge Graph, Creative Studio, image readiness, and integration status in one place.

It is read-only for external systems. It does not call ComfyUI, Printify, Etsy, or any publishing/order API.

## What It Shows

Control Center reports:

- API status
- Job Queue counts for pending, in-progress, processed, and failed jobs
- approval-needed jobs
- Knowledge Graph file/report status and node/edge counts when available
- Creative Studio health and safety flags
- ComfyUI running/not-running status, configured URL, and detected install path
- Model Registry and Workflow Manager presence
- Image Worker execution-disabled readiness
- server config health
- integration readiness for ComfyUI, Printify, Etsy, Tasker/phone ingestion, and Outlook import
- storage path checks for JamesOSData, Knowledge Graph, Creative Studio, Queue, Reports, Phone, Email, and ChatGPT data
- GPU/ComfyUI readiness fields, including configured API URL, max concurrent image jobs, one-image-at-a-time mode, and execution disabled

## API Routes

```text
GET /control-center
GET /control-center/health
GET /control-center/services
GET /control-center/integrations
GET /control-center/jobs
GET /control-center/storage
GET /control-center/summary
```

All routes require the normal JamesOS API key.

`GET /control-center/summary` returns Jade-friendly sections:

- Overall status
- What is ready
- What needs attention
- Pending approvals
- Active jobs
- Integrations
- Storage
- Next suggested actions

## Report

The generated markdown report lives at:

```text
~/JamesOSData/JamesOS/Reports/Control Center.md
```

Calling `GET /control-center` refreshes this report.

## Jade UI

Jade includes a lightweight Control Center screen opened from the chat header. It keeps Chat as the primary surface and renders the human-readable summary sections from `GET /control-center/summary`.

## Safety Model

Control Center makes the automation boundary visible:

- ComfyUI execution is false.
- Printify execution is false.
- Etsy execution is false.
- publishing is false.
- ordering is false.
- sending is false.
- approval-first automation remains required.

The Control Center can show that an integration is planned or configured, but planned/configured does not mean executable. Execution must be implemented intentionally in a later phase and routed through approval-gated jobs.

## System Flow

Control Center sits across the JamesOS pipeline:

```text
Evidence -> Knowledge Graph -> Reasoner -> Planner -> Job Queue -> Workers / Creative Studio
```

Evidence comes from notes, email/calendar imports, ChatGPT history, reports, phone ingestion, files, and future draft packages. The Knowledge Graph and Working Memory organize that evidence. The Reasoner answers through Jade, the Planner proposes queued work, and the Job Queue enforces approval before consequential automation. Workers are registered but do not execute yet. Creative Studio builds on the queue for future draft-only creative work. Image Worker plans remain disabled and approval-gated.

Control Center does not replace those systems. It gives James a compact view of whether they are present, healthy, and still safe.
