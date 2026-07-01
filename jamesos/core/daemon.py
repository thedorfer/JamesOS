import json
import shutil
import time
from datetime import datetime

from jamesos.core.queue import PENDING, PROCESSED, FAILED, ensure_queue_dirs, list_pending_jobs
from jamesos.services.intake import intake_item
from jamesos.services.job_engine import run_job


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
        try:
            results.append(_process_job(path))
        except Exception as exc:
            failed_path = FAILED / path.name
            shutil.move(str(path), str(failed_path))
            results.append(f"Failed job {path.name}: {exc}")

    return "\n".join(results)


def run_daemon(interval_seconds: int = 30) -> None:
    ensure_queue_dirs()
    print("JamesOS daemon started.")

    while True:
        result = run_once()
        if result != "No pending jobs.":
            print(result, flush=True)

        time.sleep(interval_seconds)
