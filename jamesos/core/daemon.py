import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.config.loader import daemon_interval_seconds, plugin_enabled, plugin_interval_seconds
from jamesos.core.queue import IN_PROGRESS, PROCESSED, FAILED, ensure_queue_dirs, list_pending_jobs
from jamesos.services.intake import intake_item
from jamesos.services.job_engine import run_job
from jamesos.integrations.gmail_importer import finalize_gmail_thread
from jamesos.services.archive_plugins import archive_gmail_inbox_notes, archive_calendar_inbox_notes
from jamesos.integrations.calendar_importer import import_google_calendar
from jamesos.services.contacts_plugin import build_people_profiles

SCHEDULER_STATE = VAULT / "JamesOS" / "Database" / "scheduler_state.json"


def _load_state() -> dict:
    SCHEDULER_STATE.parent.mkdir(parents=True, exist_ok=True)
    if not SCHEDULER_STATE.exists():
        return {"plugins": {}}
    return json.loads(SCHEDULER_STATE.read_text(encoding="utf-8"))


def _save_state(state: dict) -> None:
    SCHEDULER_STATE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULER_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _process_job(path):
    job = json.loads(path.read_text(encoding="utf-8"))
    job_type = job.get("type")
    payload = job.get("payload", {})

    if job_type == "intake":
        result = intake_item(
            title=payload.get("title", "Untitled Intake"),
            content=payload.get("content", ""),
            source=payload.get("source", "queue"),
            source_detail=payload.get("source_detail", ""),
        )
    elif job_type == "refresh":
        result = run_job("refresh_all")
    else:
        raise ValueError(f"Unknown job type: {job_type}")

    job["status"] = "processed"
    job["processed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job["result"] = result

    gmail_meta = payload.get("gmail", {})
    if gmail_meta.get("thread_id"):
        finalize_result = finalize_gmail_thread(gmail_meta["thread_id"])
        job["gmail_finalized"] = finalize_result

    target = PROCESSED / path.name
    target.write_text(json.dumps(job, indent=2), encoding="utf-8")
    path.unlink()

    return result


def run_once() -> str:
    ensure_queue_dirs()
    jobs = list_pending_jobs()

    if not jobs:
        return "No pending jobs."

    results = []

    for path in jobs:
        claimed = IN_PROGRESS / path.name

        try:
            path.rename(claimed)
        except FileNotFoundError:
            continue

        try:
            results.append(_process_job(claimed))
        except Exception as exc:
            failed_path = FAILED / claimed.name
            if claimed.exists():
                shutil.move(str(claimed), str(failed_path))
            results.append(f"Failed job {claimed.name}: {exc}")

    return "\n".join(results)


def run_scheduled_plugins() -> str:
    from jamesos.integrations.gmail_importer import import_gmail_label

    scheduled = {
        "gmail": import_gmail_label,
        "archive_gmail": archive_gmail_inbox_notes,
        "archive_calendar": archive_calendar_inbox_notes,
        "calendar": import_google_calendar,
        "contacts": build_people_profiles,
    }

    state = _load_state()
    plugin_state = state.setdefault("plugins", {})
    now = time.time()
    results = []

    for name, func in scheduled.items():
        if not plugin_enabled(name):
            continue

        interval = plugin_interval_seconds(name, 0)
        if interval <= 0:
            continue

        last_run = float(plugin_state.get(name, {}).get("last_run_epoch", 0))
        if now - last_run < interval:
            continue

        result = func()
        plugin_state[name] = {
            "last_run_epoch": now,
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result": result,
        }
        results.append(f"Scheduled plugin {name}: {result}")

    _save_state(state)

    return "\n".join(results) if results else "No scheduled plugins due."


def run_daemon(interval_seconds: int | None = None) -> None:
    ensure_queue_dirs()

    if interval_seconds is None:
        interval_seconds = daemon_interval_seconds()

    print(f"JamesOS daemon started. Interval: {interval_seconds}s", flush=True)

    while True:
        queue_result = run_once()
        if queue_result != "No pending jobs.":
            print(queue_result, flush=True)

        scheduled_result = run_scheduled_plugins()
        if scheduled_result != "No scheduled plugins due.":
            print(scheduled_result, flush=True)

        time.sleep(interval_seconds)
