# JamesOS Control Center

The Control Center is the server/admin readiness layer for JamesOS. It gathers local health, storage, queue, Knowledge Graph, Creative Studio, and integration status in one place.

It is read-only for external systems. It does not call ComfyUI, Printify, Etsy, or any publishing/order API.

## What It Shows

Control Center reports:

- API status
- Job Queue counts for pending, in-progress, processed, and failed jobs
- approval-needed jobs
- Knowledge Graph file/report status and node/edge counts when available
- Creative Studio health and safety flags
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
```

All routes require the normal JamesOS API key.

## Report

The generated markdown report lives at:

```text
~/JamesOSData/JamesOS/Reports/Control Center.md
```

Calling `GET /control-center` refreshes this report.

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
Evidence -> Knowledge Graph -> Reasoner -> Planner -> Job Queue -> Creative Studio
```

Evidence comes from notes, email/calendar imports, ChatGPT history, reports, phone ingestion, files, and future draft packages. The Knowledge Graph and Working Memory organize that evidence. The Reasoner answers through Jade, the Planner can create queued work, and the Job Queue enforces approval before consequential automation. Creative Studio builds on that queue for future draft-only creative work.

Control Center does not replace those systems. It gives James a compact view of whether they are present, healthy, and still safe.
