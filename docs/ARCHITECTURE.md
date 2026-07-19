# Architecture

Last reviewed: 2026-07-19

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

FastAPI, Ollama, GPU/image work, commerce-provider access, and private data run on the Linux desktop. The ThinkBook is a browser, SSH/tunnel, and development client—not a production execution host. Android remains a planned secondary client; the desktop web shell is primary.

The primary route is `/app`. The server defines allowed views, components, commands, and state transitions. The browser never calls Ollama or providers directly, and model output cannot supply executable HTML, JavaScript, CSS selectors, shell commands, or arbitrary URLs. External writes use scoped authorization and immutable resource binding. Product Studio's Generate button authorizes only the bounded unpublished-draft workflow; publication remains separately protected.

The systemd user service is installed and enabled at `~/.config/systemd/user/jamesos.service`; user lingering is enabled. Tailscale Serve is the recommended private-access design, but its current deployment is unverified. Public exposure and Funnel are not configured.

Private machine data belongs beneath `~/JamesOSData`, outside Git. Layouts live beneath `~/JamesOSData/JamesOS/Layouts/`. See [Security](SECURITY_MODEL.md) and [Web application](WEB_APPLICATION.md).
