# Service operations

Last reviewed: 2026-07-19

The installed user unit is `~/.config/systemd/user/jamesos.service`, with working directory `%h/JamesOS`, executable `%h/JamesOS/.venv/bin/python -m scripts.api_server`, and optional environment file `%h/JamesOSData/JamesOS/runtime.env`. Never document that file's contents. The unit is enabled and user lingering is enabled so JamesOS is intended to remain running after terminal sessions close.

```bash
systemctl --user daemon-reload
systemctl --user enable --now jamesos
systemctl --user start jamesos
systemctl --user stop jamesos
systemctl --user restart jamesos
systemctl --user status jamesos
journalctl --user -u jamesos -f
loginctl show-user james -p Linger
curl --fail http://127.0.0.1:8787/health
```

For ThinkBook access, tunnel the local port: `ssh -N -L 8787:127.0.0.1:8787 james@DESKTOP`. Open `http://127.0.0.1:8787/app` locally. A separately reviewed Tailscale Serve configuration may proxy to loopback; its current deployment is unverified. Never bind JamesOS directly to the public internet or enable Funnel.

Deployment should preserve the previous known-good commit, run tests, restart, inspect health/logs, and roll back the code revision plus restart if acceptance fails. Provider actions require their normal confirmations after every restart.
