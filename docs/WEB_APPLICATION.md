# Web application

Last reviewed: 2026-07-18

The recovery branch implements the main browser route at `/app`; acceptance and promotion to master are pending.

The shell keeps JamesOS conversation mounted on the left and renders the selected deterministic workspace on the right. On narrow screens chat becomes a drawer. The Context Dock is the primary navigation. A compact status dot opens local health details for API, Ollama, GPU, image worker, private storage, and commerce-profile readiness.

Chat requests go from the browser to the local FastAPI API. FastAPI supplies bounded profile/form context to the desktop Ollama integration, validates structured output, and returns only allowlisted commands. Rendering uses registered components and text-safe DOM updates. The browser does not contact Ollama or a provider directly.

Workspace edits are local and support Undo. “Generate it” creates a pending confirmation; it does not submit automatically. Publishing remains behind the existing destination-specific confirmation. Errors become safe visible state. Job status polling changes views only on meaningful generation, review-ready, or failure transitions; server-sent events are planned after polling is stable.

See [Workspace Engine](WORKSPACE_ENGINE.md), [Context Dock](CONTEXT_DOCK.md), and [Layout Manager](LAYOUT_MANAGER.md).
