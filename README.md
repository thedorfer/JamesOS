# JamesOS

JamesOS is a local-first, agent-driven Linux workspace operating environment. Its primary interface is a chat-led web application with deterministic workspaces, configurable dashboards, The Agency, explicit external-action approvals, and profile-bound commerce automation.

> Current branch status: the web-first shell is implemented on `recovery/workspace-engine-20260718` and this documentation branch, but is not merged to `master`. See [Current status](docs/CURRENT_STATUS.md).

## Interface

<!-- Screenshot placeholder: add an accepted `/app` desktop capture after recovery-branch promotion. -->

- Persistent JamesOS conversation pane on the left.
- Contextual, customizable workspace on the right.
- Context Dock as primary navigation, with locked Home, The Agency, and Admin anchors.
- Compact health indicator and profile-bound commerce controls.
- Visible confirmations before consequential external actions.

```text
ThinkBook browser / SSH
          |
      SSH tunnel
          |
Linux desktop execution host
  ├── JamesOS FastAPI service (/app)
  ├── Workspace Engine, Context Dock, Layout Manager
  ├── Ollama and ComfyUI / GPU workers
  ├── private ~/JamesOSData
  └── confirmed provider integrations
```

The ThinkBook is a browser, SSH, tunnel, and development client. Production JamesOS, Ollama, GPU/image work, private data, and provider access belong on the Linux desktop. Android and Jade are later secondary clients.

## Quick start

```bash
cd ~/JamesOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.api_server
```

Open `http://127.0.0.1:8787/app` on the desktop. From the ThinkBook, use an SSH tunnel; never expose JamesOS directly to the public internet. See [Desktop setup](docs/SETUP_DESKTOP.md).

When the user service is installed:

```bash
systemctl --user start jamesos
systemctl --user stop jamesos
systemctl --user restart jamesos
systemctl --user status jamesos
journalctl --user -u jamesos -f
```

## Current and planned

| Area | Status on this branch |
| --- | --- |
| `/app`, Workspace Engine, Context Dock, Layout Manager | Implemented; awaiting desktop acceptance and promotion |
| Shell health and compact commerce profile selector | Implemented; awaiting desktop acceptance and promotion |
| Profile-bound unpublished commerce workflow | Implemented across `master` and recovery work; end-to-end acceptance remains |
| The Agency and Admin | Deterministic placeholder views; richer operational workspaces planned |
| Terminal, privilege broker, The Marine | Planned; no production capability yet |
| Android/Jade web companion | Planned secondary client |

Commerce generation creates an unpublished draft, never an order. Publication requires an explicit destination-specific confirmation. Job destinations are immutable, profile defaults do not overwrite manual edits, and local validation runs before provider writes.

Start with the [documentation index](docs/INDEX.md), [architecture](docs/ARCHITECTURE.md), [web application](docs/WEB_APPLICATION.md), and [security model](docs/SECURITY_MODEL.md).

## License

See [LICENSE.md](LICENSE.md).
