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
GET /control-center/summary
```

Control Center also does not call external services.

## Current Integrations

### Brand Registry

Status: active local foundation.

Brand Registry stores shop-specific creative rules, approval rules, preferred POD providers, and integration safety flags for multiple future Etsy/POD shops. Default brands are UnityStitches and a disabled Degen Market Chaos placeholder.

Routes:

```text
GET /brands
GET /brands/health
GET /brands/default
GET /brands/{brand_id}
POST /brands/{brand_id}/validate
```

It does not call Etsy, Printify, ComfyUI, upload, publish, order, or send anything.

### POD Provider Registry

Status: active local foundation.

POD Provider Registry lists Printify and InkedJoy as configurable provider targets. It is read-only and does not call either provider. Printify is the active planned POD provider for the MVP automated shop pipeline. InkedJoy remains a future/manual-upload provider foundation only.

Current shop/provider defaults:

- Bagholder Supply Co uses Printify for now.
- Cheeky Peach Prints uses Printify for now.
- UnityStitches underwear, panties, and thongs prefer Printify for now.

Routes:

```text
GET /pod-providers
GET /pod-providers/health
GET /pod-providers/{provider_id}
```

All provider records force:

```text
readonly: true
writes_enabled: false
draft_creation_enabled: false
order_enabled: false
```

InkedJoy status: future/manual-upload provider only; API access not confirmed; not active for current automation.

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

### Planner And Workers

Status: active foundation.

Planner turns intent into proposed plans and recommended jobs. The worker registry lists future addon/worker capabilities. Neither layer executes work in this phase.

```text
GET /planner/health
POST /planner/plan
GET /workers
GET /workers/{worker_name}
```

## Planned Integrations

### ComfyUI

Status: approval-gated local image execution.

JamesOS may execute exactly one approved local image job against `http://127.0.0.1:8188` and save the PNG under JamesOSData. It does not call any external provider, upload the image, create a listing, or order anything. Control Center reports the configured API URL, one-image-at-a-time readiness, and external execution flags.

### InkedJoy

Status: planned/manual-upload foundation.

JamesOS does not call InkedJoy, upload images, create products, place orders, or publish listings. Generated design PNGs are local draft assets for James review.

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

Status: read-only performance foundation plus planned approval-only sales platform.

Creative Intelligence exposes a read-only Etsy performance-history foundation for UnityStitches. It is designed for OAuth-backed shop/listing/order history later, but this phase does not create, edit, renew, deactivate, delete, publish, message, fulfill, upload, scrape, call Printify, or call ComfyUI.

Routes:

```text
GET /etsy/health
GET /etsy/auth-status
POST /etsy/sync-readonly
GET /etsy/performance
GET /etsy/top-products
GET /etsy/underperforming-products
```

Every Etsy route reports:

```text
readonly: true
writes_enabled: false
publishing_enabled: false
order_fulfillment_enabled: false
```

OAuth tokens and secrets must live outside Git. Missing credentials return `not_configured`.

Future Etsy work may prepare draft metadata and review pages. No live listings should be created without explicit approval.

### UnityStitches

Status: active draft-only foundation.

UnityStitches creates local product draft packages and a Creative Studio pipeline job for each daily run. It creates exactly one women's underwear draft and one rotating configured product draft. It does not create live products.

Routes:

```text
GET /unitystitches/health
POST /unitystitches/generate-daily-drafts
GET /unitystitches/drafts
GET /unitystitches/drafts/{date}
```

## Approval-First Safety

Integrations must default to safe local reporting or draft creation. External side effects require a Job Queue record and James approval.

Never implement hidden automatic calls for:

- Printify publishing
- Etsy live listing creation
- production orders
- email sending
- image generation intended for upload
- external purchases
