# Desktop Setup

This page describes the JamesOS desktop/server setup for local development and daily use.

## Requirements

- Linux desktop
- Python 3
- Flutter SDK for the Jade client
- Local network or Meshnet access from phone
- Optional: Ollama or other local model tooling
- Future optional: ComfyUI on the desktop GPU

## Repository

```bash
cd ~/JamesOS
git status
```

Human notes should stay in:

```text
~/Notes
```

Machine-owned JamesOS data should stay in:

```text
~/JamesOSData
```

## Python Validation

```bash
python3 -m py_compile jamesos/services/*.py scripts/*.py
python3 -m unittest discover tests
```

## API Server

Development run:

```bash
python3 scripts/api_server.py
```

Health check:

```bash
curl http://localhost:8787/health
```

Service health/config:

```bash
curl -H "X-JamesOS-Key: YOUR_KEY" http://localhost:8787/server/health
curl -H "X-JamesOS-Key: YOUR_KEY" http://localhost:8787/server/config
```

Generated server page:

```text
~/JamesOSData/JamesOS/Reports/Server Configuration.md
```

## Flutter Jade App

```bash
cd ~/JamesOS/apps/jade_app
flutter analyze
flutter run -d linux
```

Android run:

```bash
flutter run -d 58021FDCQ008QF
```

Linux builds should not call unavailable TTS/STT plugins. Android builds can keep voice input/output enabled.

## Job Queue

The Job Queue is the automation backbone:

```bash
python3 scripts/job_queue.py list
python3 scripts/job_queue.py create review.example --payload '{"draft_only": true}'
python3 scripts/job_queue.py approve JOB_ID
```

Approval-gated jobs cannot complete until approved.

## Configuration Files

Config lives under:

```text
~/JamesOSData/JamesOS/Config/
```

Important config files:

- `system.yaml`
- `plugins.yaml`
- `folders.yaml`
- `ai.yaml`
- `server.yaml`
- `integrations.yaml`

Do not store secrets in Git. Keep API keys and local secrets under JamesOSData.

## Reports

Reports are generated under:

```text
~/JamesOSData/JamesOS/Reports/
```

Useful reports:

- `Job Queue.md`
- `Server Configuration.md`
- `Daily Briefing.md`
- `Knowledge Graph.md`
- `UnityStitches Product Drafts.md` when future product drafting is implemented
