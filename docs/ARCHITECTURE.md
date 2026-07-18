# Architecture

Last reviewed: 2026-07-18

```text
ThinkBook browser / SSH
          |
      SSH tunnel
          |
Linux desktop execution host
  ├── JamesOS FastAPI service
  ├── Workspace Engine
  ├── Context Dock
  ├── Layout Manager
  ├── The Agency
  ├── Ollama
  ├── ComfyUI / GPU workers
  ├── private JamesOSData
  └── confirmed provider integrations
```

FastAPI, Ollama, GPU/image work, commerce-provider access, and private data run on the Linux desktop. The ThinkBook is a browser, SSH/tunnel, and development client—not a production execution host. Android and Jade are planned secondary clients.

The primary route is `/app`. The server defines allowed views, components, commands, and state transitions. The browser never calls Ollama directly, and model output cannot supply executable HTML, JavaScript, CSS selectors, shell commands, or arbitrary URLs. Local workspace edits are reversible. External writes require visible confirmation; commerce destinations are immutable once a job is bound.

Private machine data belongs beneath `~/JamesOSData`, outside Git. Layouts live beneath `~/JamesOSData/JamesOS/Layouts/`. See [Security](SECURITY_MODEL.md) and [Web application](WEB_APPLICATION.md).
