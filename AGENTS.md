# JamesOS Codex Guide

## Project shape

JamesOS is a personal OS/assistant project with two main parts:

- `jamesos/` and `scripts/`: Python backend, FastAPI API, importers, ingestion, memory/search services.
- `apps/jade_app/`: Flutter client for Android, Linux, and eventually iOS.

## Important storage rules

- Human notes live in `~/Notes`.
- Machine-owned JamesOS data lives in `~/JamesOSData`.
- Do not put large archives, queues, imports, vector indexes, or raw processed data back into `~/Notes`.
- Existing Python services use `jamesos.config.VAULT`, currently pointing to `~/JamesOSData`.

## Common commands

From repo root:

```bash
cd ~/JamesOS
git status
git pull
python3 -m py_compile jamesos/config.py jamesos/services/jade_reasoner.py
systemctl --user restart jamesos-api.service jamesos-daemon.service
curl http://localhost:8787/health
```

Flutter app:

```bash
cd ~/JamesOS/apps/jade_app
flutter clean
flutter pub get
flutter analyze
flutter run -d linux
flutter run -d 58021FDCQ008QF
```

Deploy helper:

```bash
cd ~/JamesOS
deploy-jamesos
```

## Current priorities

1. Jade must be useful, not just chatty.
2. Memory mode should search imported ChatGPT history first.
3. In Memory mode, do not route user questions to weather/tools unless explicitly requested.
4. Linux builds should not call TTS/STT plugins because those plugins are unavailable on Linux.
5. Phone/Android builds should keep voice input/output enabled.
6. Keep the app name as `Jade`.

## Recent data imported

The ChatGPT export imported approximately:

- 2,541 conversations
- 50,565 messages
- 1,844 candidate memories
- 2,276 candidate decisions

The search index is expected at:

```text
~/JamesOSData/JamesOS/Brain/ChatGPT/Index/conversations_index.jsonl
```

## Known bug to fix next

A question like:

```text
What do you know about Malcolm from my ChatGPT history?
```

has incorrectly returned weather. Fix by ensuring Memory mode and ChatGPT-history wording bypasses weather/tool routing and uses `chatgpt_history_search` first.

## Style

- Prefer small safe patches.
- Run analyzers/compilers after changes.
- Keep UI concise and practical.
- Do not expose raw file paths or JSON to the user unless they ask.
- Do not delete user data without a backup or explicit confirmation.
