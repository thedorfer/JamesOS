# JamesOS

JamesOS is a local-first, web-first personal operating environment. The Linux desktop is the execution host; a ThinkBook or other client connects as a browser, SSH, tunnel, and development client.

The primary interface is `/app`, a persistent Jade chat pane beside contextual workspaces for Home, The Agency, Admin, Product Studio, commerce diagnostics, and review. Legacy commerce URLs redirect to `/app?view=commerce.new`.

Product Studio destinations use enabled `commerce_shop` profiles rather than hard-coded shops.

> Read [Current status](docs/CURRENT_STATUS.md) before relying on a feature. It distinguishes implementation and automated tests from manual acceptance and real-provider validation.

## Runtime architecture

```text
ThinkBook browser / SSH / development client
                       |
             SSH tunnel or reviewed private access
                       |
Linux desktop execution host
  ├── JamesOS FastAPI and /app
  ├── Ollama (mistral:instruct)
  ├── GPU, ComfyUI, and local image services
  ├── provider integrations
  ├── private ~/JamesOSData
  └── enabled systemd user service
```

JamesOS uses `~/.config/systemd/user/jamesos.service`. User lingering is enabled so the service is intended to remain available after terminal sessions close. Source work is developed in Git branches and deliberately deployed to the desktop.

## Current implementation

| Area | Evidence-based status |
| --- | --- |
| `/app` shell, Home, navigation, health, layouts | Implemented and test-covered; manually exercised |
| Jade/Ollama chat and attachments | Implemented and test-covered; manually working with known intent/noise defects |
| Private chat | Implemented and test-covered |
| Adult mode | Implemented and test-covered; manually blocked by a UI/policy-state defect |
| The Agency registry | Implemented and test-covered; marketplace entries remain planned |
| Admin and EHF | Implemented and test-covered |
| Product Studio local typography and preflight | Implemented and test-covered |
| Real browser-to-Printify unpublished-draft flow | **Manual acceptance failed; not validated end to end** |
| Browser terminal, privilege broker, The Marine | Planned; not implemented |

Automated fake-provider tests are not evidence of successful real-provider execution. The latest real Product Studio attempt produced no candidate and no Printify draft. Nothing was published and no order was created.

## Quick start

```bash
cd ~/JamesOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.api_server
```

Open `http://127.0.0.1:8787/app` on the desktop. For private remote access, use an SSH tunnel or a separately verified Tailscale Serve deployment. Public exposure and Tailscale Funnel are not configured.

```bash
systemctl --user status jamesos
systemctl --user restart jamesos
curl --fail http://127.0.0.1:8787/health
```

Start with the [documentation index](docs/INDEX.md), [current status](docs/CURRENT_STATUS.md), [architecture](docs/ARCHITECTURE.md), [web application](docs/WEB_APPLICATION.md), and [security model](docs/SECURITY_MODEL.md).

## License

See [LICENSE.md](LICENSE.md).
