# ComfyUI Local Service

ComfyUI is the local image renderer for approved JamesOS creative image jobs. JamesOS can check health, prepare plans, and execute one explicitly approved local image job at a time.

## Install Paths

Preferred path:

```text
~/AI/ComfyUI
```

Legacy path detected by JamesOS:

```text
~/ComfyUI
```

## Localhost Only

Run ComfyUI on localhost only:

```text
http://127.0.0.1:8188
```

Do not expose ComfyUI on a public interface unless a future security review explicitly approves it.

## GTX 1080 Ti Notes

The desktop target is NVIDIA GTX 1080 Ti. Prefer:

- low VRAM mode
- one image job at a time
- practical first-pass product design sizes
- workflows tested for Pascal-era CUDA behavior
- Torch 2.5.1 + CUDA 12.1 where practical for the local environment

Example launch:

```bash
cd ~/AI/ComfyUI
python3 main.py --listen 127.0.0.1 --port 8188 --lowvram
```

## systemd --user Example

Create:

```text
~/.config/systemd/user/comfyui.service
```

Example:

```ini
[Unit]
Description=ComfyUI local service
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/AI/ComfyUI
ExecStart=/usr/bin/python3 main.py --listen 127.0.0.1 --port 8188 --lowvram
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Enable/start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now comfyui.service
```

Check:

```bash
curl http://127.0.0.1:8188/system_stats
```

## JamesOS Safety Boundary

Current implementation:

- health check and system stats
- approved single-image prompt queue execution
- local output download only
- no Printify calls
- no Etsy calls
- no publishing
- no ordering
- no uploads
- no sending

Execution must be approval-gated through Planner, Creative Intelligence, Creative Studio Pipeline, Image Worker, and Job Queue.
