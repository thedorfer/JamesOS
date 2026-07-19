# Desktop setup

Last reviewed: 2026-07-19

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

JamesOS uses the reviewed unit at `~/.config/systemd/user/jamesos.service`, with working directory `%h/JamesOS`, executable `%h/JamesOS/.venv/bin/python -m scripts.api_server`, and optional `%h/JamesOSData/JamesOS/runtime.env`. Do not commit or print environment contents.

```bash
systemctl --user daemon-reload
systemctl --user enable --now jamesos
loginctl enable-linger james
systemctl --user status jamesos
journalctl --user -u jamesos -f
```

The unit and user lingering are enabled. Verify health after every deliberate deployment. See [Service operations](SERVICE_OPERATIONS.md).

## ThinkBook tunnel

```bash
ssh -N -L 8787:127.0.0.1:8787 james@DESKTOP
```

Browse to `http://127.0.0.1:8787/app` on the ThinkBook. Never expose JamesOS directly to the public internet.

## Private-network access

Access defaults to `loopback`; in that mode the server binds `127.0.0.1` and rejects non-loopback clients, hosts, and origins. Optional settings are read from `~/JamesOSData/JamesOS/runtime.env`:

```dotenv
JAMESOS_ACCESS_MODE=tailnet
JAMESOS_TRUSTED_HOSTS=james.example-tailnet.ts.net
JAMESOS_TRUSTED_ORIGINS=https://james.example-tailnet.ts.net
JAMESOS_ALLOWED_NETWORKS=
```

Use `tailnet` only with Tailscale Serve proxying to the loopback listener. Configure the exact HTTPS origin and Host value; do not use wildcards. JamesOS accepts Tailscale identity headers only on the direct loopback proxy connection and does not treat arbitrary forwarded headers as authentication. Tailscale Funnel/public sharing is out of scope and must remain disabled. Repository evidence does not currently verify that Serve is deployed on the desktop.

`lan` mode binds broadly only when trusted hosts, trusted origins, and explicit CIDRs are all valid. It never allows all RFC1918 networks implicitly:

```dotenv
JAMESOS_ACCESS_MODE=lan
JAMESOS_TRUSTED_HOSTS=james-desktop.lan:8787
JAMESOS_TRUSTED_ORIGINS=http://james-desktop.lan:8787
JAMESOS_ALLOWED_NETWORKS=192.168.50.0/24
```

Plain HTTP LAN access is visibly warned and should be replaced with private HTTPS where practical. Unsafe or incomplete configuration fails closed. These settings do not weaken CSRF, provider confirmations, immutable destinations, publication safeguards, system locks, or the no-order guarantee.

## Restart and rollback

Run tests, preserve the known-good commit, restart the user service, inspect `/health`, `/app`, and logs, and roll back the Git revision plus restart if acceptance fails. Restarting never bypasses provider confirmation or immutable job binding.
