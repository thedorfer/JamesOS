# Phone Ingestion

JamesOS can ingest phone-adjacent data from a Linux Mint desktop or laptop without requiring Tasker.

Safety rules:

- No phone deletion.
- No sending messages.
- No cloud upload by default.
- No provider writes.
- Tasker is optional.

## Methods

### Android USB/MTP Pull From Linux Mint

Mount the phone over USB/MTP and copy selected folders such as screenshots, photos, downloads, exported chats, or app export files into a local JamesOS intake folder.

This is best for manual review, bulk backfills, and keeping control on the desktop/laptop.

### Syncthing Folder Sync

Use Syncthing to keep selected phone folders mirrored to a local Linux folder. JamesOS can then import from the local mirror.

This keeps the flow local-first and avoids cloud upload by default.

### KDE Connect

Use KDE Connect for local-network file sharing and optional notification visibility. JamesOS should ingest only local exported files or explicitly shared files.

### ADB Pull

Use `adb pull` for screenshots, photos, downloads, or app export folders when USB debugging is intentionally enabled.

ADB should be pull-only for JamesOS ingestion. Do not delete files from the phone.

### Tasker Optional Push

Tasker can still POST call, SMS, notification, and app event payloads to JamesOS, but it is no longer the only architecture.

## API

```text
GET /phone-ingestion/health
GET /phone-ingestion/methods
```

These routes report available ingestion methods and safety flags. They do not pull files, delete data, send messages, or upload to cloud services.
