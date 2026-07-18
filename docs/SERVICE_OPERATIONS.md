# Service operations

Last reviewed: 2026-07-18

The intended user unit is `~/.config/systemd/user/jamesos.service`, with working directory `%h/JamesOS`, executable `%h/JamesOS/.venv/bin/python -m scripts.api_server`, and optional environment file `%h/JamesOSData/JamesOS/runtime.env`. Never document that file's contents.

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

On 2026-07-18, linger was enabled but the unit was not present/active; installation and acceptance remain outstanding.

For ThinkBook access, tunnel the local port: `ssh -N -L 8787:127.0.0.1:8787 james@DESKTOP`. Open `http://127.0.0.1:8787/app` locally. Never bind JamesOS directly to the public internet.

Deployment should preserve the previous known-good commit, run tests, restart, inspect health/logs, and roll back the code revision plus restart if acceptance fails. Provider actions require their normal confirmations after every restart.
