# Workers

The worker registry is the foundation for future JamesOS workers, addons, and plugins.

Current implementation is a registry only. It lists workers, supported job types, and safety notes. It does not execute workers.

## API

```text
GET /workers
GET /workers/{worker_name}
```

## Initial Workers

- `knowledge_graph_worker`
- `creative_studio_worker`
- `image_worker`
- `workflow_manager`
- `model_registry`
- `comfyui_client`
- `comfyui_worker`
- `unitystitches_worker`
- `printify_worker`
- `etsy_worker`
- `phone_ingestion_worker`
- `briefing_worker`

Each worker has:

- name
- status
- enabled
- execution enabled
- supported job types
- safety notes

## Execution Policy

All workers currently report `execution_enabled: false`.

Workers should eventually consume approved Job Queue items. They must not bypass the Planner, Job Queue, approval state, or Control Center safety model.

External integrations remain disabled:

- no ComfyUI execution
- no Printify API calls
- no Etsy API calls
- no publishing
- no ordering
- no sending
