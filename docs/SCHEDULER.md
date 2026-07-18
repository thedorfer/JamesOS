# JamesOS Scheduler — Phase 1

Last reviewed: 2026-07-18. Scheduled work is evaluated through the Linux desktop service. Scheduling never bypasses an external-write, provider, publication, order, terminal, or privilege approval; work that requires confirmation waits for that confirmation rather than scheduling around it.

The scheduler determines when declarative work is due and enqueues a normal JamesOS Job Queue item for each confirmed occurrence. It does not execute jobs, call agents, approve work, run shell commands, contact providers, or perform external side effects.

```text
schedule definition
→ deterministic due-time evaluation
→ occurrence identity
→ existing Job Queue
→ existing approval and worker pipeline
```

## Schedule types

- `once`: one timezone-aware RFC3339 instant; completes after enqueue or a skipped expired occurrence.
- `hourly`: a positive interval anchored to a timezone-aware instant. Occurrences never drift with evaluator timing.
- `daily`: a local `HH:MM` in the declared IANA timezone.
- `weekly`: a local time on one or more unique `MO` through `SU` weekday codes.

All derived occurrence timestamps are stored as UTC RFC3339. The machine timezone is never used. During a fall-back ambiguity, the first local occurrence (`fold=0`) is selected and the second fold is not queued. During a spring-forward gap, the occurrence advances minute-by-minute to the first valid local instant after the gap.

## Preview and confirmation

Creation, enablement, disablement, and ticks preview by default. Durable local mutation requires `--confirm-create`, `--confirm`, or `--confirm-enqueue` respectively.

```bash
python scripts/jamesos.py schedule create \
  --name "Morning career review" \
  --timezone America/Chicago \
  --daily-at 08:00 \
  --job-template-file schedule-job.json

python scripts/jamesos.py schedule list
python scripts/jamesos.py schedule show --schedule-id SCHEDULE_ID
python scripts/jamesos.py schedule preview --schedule-id SCHEDULE_ID --count 5
python scripts/jamesos.py schedule tick
python scripts/jamesos.py schedule tick --confirm-enqueue
python scripts/jamesos.py schedule disable --schedule-id SCHEDULE_ID --confirm
python scripts/jamesos.py schedule enable --schedule-id SCHEDULE_ID --confirm
```

The job-template file contains declarative `job_type`, `title`, object `payload`, and `requires_approval`. It may optionally declare a capability, opaque profile reference, priority, and tags. Credentials, secret-like keys, callbacks, commands, callables, and absolute paths are rejected. List and status output show only a payload digest and safe template summary.

## Idempotency and misfires

Each occurrence ID is a SHA-256 derived from the schedule schema, opaque schedule ID, and normalized UTC scheduled time. Scheduler occurrence evidence and Job Queue scheduling provenance carry this same ID. A restart checks both stores before enqueueing, so an accepted occurrence is not duplicated even if scheduler persistence was interrupted.

One schedule can enqueue at most one job per tick. `fire_once` queues only the latest missed occurrence and summarizes earlier misses. `skip` records and advances an occurrence older than its configured grace period without enqueueing. Queue failure does not advance or mark the occurrence successful, and there is no automatic retry.

## Private storage

Production state is under `~/JamesOSData/JamesOS/Scheduler`:

```text
Scheduler/
  schedules/SCHEDULE_ID.json
  occurrences/SCHEDULE_ID/OCCURRENCE_ID.json
```

Directories use mode `0700`; files use `0600` and atomic replacement. Symlink traversal, path traversal, plaintext credentials, and silent history deletion are prohibited.

Future phases may add a separately reviewed persistent runner, systemd integration, and Jade UI. Phase 1 installs no timers, cron entries, services, autostart configuration, or background process.
