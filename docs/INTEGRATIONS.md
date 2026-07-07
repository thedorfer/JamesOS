# Integrations

This page summarizes JamesOS integration boundaries, configuration, and current implementation status.

## Configuration

Integration settings live in:

```text
~/JamesOSData/JamesOS/Config/integrations.yaml
```

Server settings live in:

```text
~/JamesOSData/JamesOS/Config/server.yaml
```

Health/config routes:

```text
GET /server/config
GET /server/health
GET /server/page
```

These routes report local configuration and safety status. They do not call external services.

Control Center routes provide the combined admin/readiness view:

```text
GET /control-center
GET /control-center/integrations
GET /control-center/jobs
GET /control-center/storage
```

Control Center also does not call external services.

## Current Integrations

### Jade Flutter App

Status: active local client.

Jade talks to the JamesOS API with an API key and presents chat, work, private, dashboard, attachment, and Knowledge Graph interactions.

### Tasker Phone Ingestion

Status: supported.

Android Tasker can POST phone events to:

```text
POST /phone-ingest
```

See [Phone Ingestion Tasker](PHONE_INGESTION_TASKER.md).

### Email And Calendar Imports

Status: local import foundations exist.

Email/calendar evidence can feed reports, timelines, search, Knowledge Graph, and reasoner context. Imported evidence remains local under JamesOSData.

### Job Queue

Status: active foundation.

The queue stores approval-gated automation jobs. Future integrations should use the queue before taking consequential action.

### Control Center

Status: active foundation.

Control Center summarizes integration readiness, queue counts, approval-needed jobs, service health, and storage checks. It is meant to make automation readiness visible while keeping execution flags false until a later phase explicitly implements them.

## Planned Integrations

### ComfyUI

Status: configured/readiness only, not running from JamesOS.

No execution is implemented yet. Control Center reports the configured API URL, max concurrent image jobs, one-image-at-a-time readiness, and `execution_enabled: false`. Future use should run locally against the desktop ComfyUI API and save generated PNG assets under JamesOSData.

### Printify

Status: planned draft-only target.

Future placeholder operations:

- list shops
- list blueprints
- find product blueprint
- upload artwork
- create product draft

Rules:

- do not publish
- do not order
- do not send to production
- require James approval
- keep Control Center execution and publish flags false until intentionally implemented

### Etsy

Status: planned approval-only sales platform.

Future Etsy work should prepare draft metadata and review pages. No live listings should be created without explicit approval.

Control Center reports Etsy as not configured and non-executable in this phase.

### UnityStitches

Status: roadmap.

UnityStitches is planned as an inclusive product draft pipeline for Etsy/Printify. It should create draft packages, not live products.

## Approval-First Safety

Integrations must default to safe local reporting or draft creation. External side effects require a Job Queue record and James approval.

Never implement hidden automatic calls for:

- Printify publishing
- Etsy live listing creation
- production orders
- email sending
- image generation intended for upload
- external purchases
