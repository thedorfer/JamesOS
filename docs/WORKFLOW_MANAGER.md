# Workflow Manager

The Workflow Manager selects and validates future ComfyUI workflows without executing them.

Responsibilities:

- list workflows
- get a workflow by name
- validate whether a configured workflow path exists
- choose a workflow for a creative package
- return `execution_enabled: false`

It does not submit prompts, queue ComfyUI jobs, upload images, or publish anything.

API routes:

```text
GET /workflows
GET /workflows/{workflow_name}
```

