# Integrations

This page summarizes JamesOS integration boundaries, configuration, and current implementation status.

## Configuration

Integration settings live under the private runtime data root:

```text
~/JamesOSData/JamesOS/Config/integrations.yaml
~/JamesOSData/JamesOS/Config/server.yaml
```

Private commerce profiles, account identifiers, product identifiers, protected resources, OAuth files, and credentials must remain outside Git.

## Health And Control Center

```text
GET /server/config
GET /server/health
GET /server/page
GET /control-center
GET /control-center/integrations
GET /control-center/jobs
GET /control-center/storage
GET /control-center/summary
```

These routes report local configuration and safety status. They do not silently perform external actions.

## Current Integrations

### Brand And Profile Registry

Status: active local foundation.

The registry stores shop-specific creative rules, approval policy, provider selection, and integration safety flags. Public code provides generic schemas and validation; identifying deployment data belongs in private local profiles.

### POD Provider Registry

Status: active foundation.

The registry represents provider capabilities and safety policy. Provider records default to read-only or dry-run behavior until a private profile and explicit confirmation enable a supported operation.

### Jade Flutter App

Status: active local client.

Jade talks to the JamesOS API and presents chat, work, private, dashboard, attachment, Knowledge Graph, and automation-review interactions.

### Tasker Phone Ingestion

Status: supported.

Android Tasker can POST phone events to:

```text
POST /phone-ingest
```

### Email And Calendar Imports

Status: local import foundations exist.

Imported evidence can feed reports, timelines, search, Knowledge Graph, and reasoner context.

### Job Queue

Status: active foundation.

The queue stores approval-gated automation jobs and durable side-effect evidence.

### Planner And Workers

Status: active foundation.

Planner turns intent into proposed plans. Worker and agent registries define bounded capabilities and route work without exposing credentials.

### ComfyUI

Status: approval-gated local image execution.

JamesOS may execute an explicitly approved local image job and save the result under JamesOSData. It does not make that image public without a separate guarded commerce workflow.

### Printify

Status: guarded provider integration.

Implemented capabilities include:

- shop and catalog reads
- artwork upload
- product draft creation and update
- variant enforcement
- mockup retrieval
- guarded publication
- recovery without duplicate completed side effects

Rules:

- explicit confirmation for remote writes
- one automatic attempt maximum
- no hidden retries
- protected resources enforced from private profiles
- no order creation

### Etsy

Status: guarded marketplace integration.

Implemented capabilities include:

- OAuth authorization and refresh
- listing reads
- listing resolution after provider publication
- deactivation for staged review
- inactive-state verification
- active-state verification

Rules:

- no publication without the required approval reference
- no hidden activation or deactivation
- credentials remain outside Git
- no order fulfillment from this workflow

## Generic Commerce Profiles

A private `commerce_shop` profile can bind:

```text
marketplace  → EtsyAgent
fulfillment  → PrintifyAgent
orchestrator → CommerceAgent
```

It may independently configure:

- `approval_mode`: `single_final` or `staged`
- final marketplace state: `active` or `inactive`
- review location
- whether a non-public provider draft may be created before final approval
- publication policy
- protected resources

## Approval-First Safety

Integrations must default to safe local reporting, dry plans, or non-public drafts. Consequential external side effects require the proper approval and explicit confirmation.

Never commit:

- shop names
- account IDs
- product or listing IDs
- protected resource IDs
- OAuth tokens
- shared secrets
- private artwork or live job reports
