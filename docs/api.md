# JamesOS REST API

Default local URL:

```text
http://localhost:8787
```

Production/user service may also be available on the desktop LAN or Meshnet address.

Most endpoints require:

```text
X-JamesOS-Key: <api key>
```

## Core

```text
GET  /health
GET  /server/config
GET  /server/health
GET  /server/page
```

`/server/page` writes:

```text
~/JamesOSData/JamesOS/Reports/Server Configuration.md
```

## Jade

```text
POST /ask
GET  /ask?q=...
GET  /dashboard
```

## Search And Memory

```text
GET  /search?q=...
POST /memory
GET  /memory/search?q=...
GET  /graph/search?q=...
POST /graph/build
GET  /typed/search?q=...
POST /typed/build
```

Additional memory routes may be included by `scripts/api_server.py`.

## Job Queue

```text
GET  /jobs
GET  /jobs/{job_id}
POST /jobs
POST /jobs/{job_id}/approve
POST /jobs/{job_id}/fail
```

Approval-gated jobs cannot complete until approved.

## Phone And Mobile

```text
POST /phone-ingest
POST /phone/daily-summary
POST /quick-note
POST /share-link
GET  /mobile/home
```

See [Phone Ingestion](PHONE_INGESTION.md) for Linux/MTP, Syncthing, KDE Connect, ADB, and optional Tasker approaches.

## Reports And Processing

```text
GET  /daily-briefing
GET  /status-report
POST /brain/summarize-chat
POST /attachments/ingest
POST /attachments/process-pending
POST /files/build
```

## Safety

The API currently does not implement Printify publishing, Etsy publishing, ComfyUI execution, production orders, or live listing creation. Future external side effects should be routed through approval-gated Job Queue jobs.
