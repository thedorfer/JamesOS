# Planner

The Planner is the planning layer between Jade's reasoning and the Job Queue.

It converts intent into a proposed plan and recommended approval-gated jobs. It does not create jobs, execute jobs, call workers, or call external services.

## API

```text
GET /planner/health
POST /planner/plan
```

`POST /planner/plan` accepts:

```json
{
  "intent": "daily_product_generation",
  "prompt": "Generate today's Commerce Shop drafts",
  "payload": {}
}
```

It returns:

- `status`
- `intent`
- `summary`
- `requires_approval`
- `recommended_jobs`
- `next_actions`
- safety flags

## Supported Intents

- `daily_product_generation`
- `creative_image_generation`
- `knowledge_graph_rebuild`
- `briefing_generation`
- `phone_ingestion_review`

## Safety

Planner is deliberately non-executing:

- no Job Queue writes
- no ComfyUI calls
- no Printify calls
- no Etsy calls
- no publishing
- no ordering
- no sending

Future Jade flows can ask Planner for a proposed job, show it to James, and only create a Job Queue item after explicit approval.
