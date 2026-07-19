# Jade mobile client

Jade's Flutter app is an experimental secondary client for Android and later mobile platforms; `/app` is the primary interface. The Linux desktop remains the execution host for FastAPI, Ollama, GPU/ComfyUI, provider operations, and private `JamesOSData`; the app must not bypass server-defined views, locks, or external-action confirmations.

```bash
flutter pub get
flutter analyze
flutter test
flutter run -d 58021FDCQ008QF
```

The secondary-client API and synchronization contract remain planned. See [JamesOS current status](../../docs/CURRENT_STATUS.md) and [roadmap](../../docs/ROADMAP.md).
