# Desktop setup

Last reviewed: 2026-07-18

The Linux desktop is the execution host for FastAPI, Ollama, GPU/ComfyUI work, provider access, and private `~/JamesOSData`. The ThinkBook is a browser, SSH/tunnel, and development client; it does not run production workloads.

## Environment

```bash
cd ~/JamesOS
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.api_server
curl --fail http://127.0.0.1:8787/health
```

Open `http://127.0.0.1:8787/app` locally. General shell health checks API, Ollama, GPU, image worker, private storage, and commerce-profile readiness without contacting Printify or Etsy. Missing optional image generation is normally yellow; inaccessible storage or required service state is red.

## User service

Install a reviewed unit at `~/.config/systemd/user/jamesos.service` using working directory `%h/JamesOS`, executable `%h/JamesOS/.venv/bin/python -m scripts.api_server`, and optional `%h/JamesOSData/JamesOS/runtime.env`. Do not commit or print environment contents.

```bash
systemctl --user daemon-reload
systemctl --user enable --now jamesos
loginctl enable-linger james
systemctl --user status jamesos
journalctl --user -u jamesos -f
```

The 2026-07-18 audit found linger enabled but no installed/active unit, so service installation is pending acceptance. See [Service operations](SERVICE_OPERATIONS.md).

## ThinkBook tunnel

```bash
ssh -N -L 8787:127.0.0.1:8787 james@DESKTOP
```

Browse to `http://127.0.0.1:8787/app` on the ThinkBook. Never expose JamesOS directly to the public internet.

## Restart and rollback

Run tests, preserve the known-good commit, restart the user service, inspect `/health`, `/app`, and logs, and roll back the Git revision plus restart if acceptance fails. Restarting never bypasses provider confirmation or immutable job binding.
