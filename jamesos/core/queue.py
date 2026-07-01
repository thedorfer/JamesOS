import json
import uuid
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

QUEUE_ROOT = VAULT / "JamesOS" / "Queue"
PENDING = QUEUE_ROOT / "pending"
PROCESSED = QUEUE_ROOT / "processed"
FAILED = QUEUE_ROOT / "failed"


def ensure_queue_dirs() -> None:
    for folder in [PENDING, PROCESSED, FAILED]:
        folder.mkdir(parents=True, exist_ok=True)


def enqueue_job(job_type: str, payload: dict) -> str:
    ensure_queue_dirs()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    job = {
        "id": job_id,
        "type": job_type,
        "created_at": now,
        "status": "pending",
        "payload": payload,
    }

    path = PENDING / f"{job_id}.json"
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    return f"Queued job: {job_id}"


def list_pending_jobs() -> list[Path]:
    ensure_queue_dirs()
    return sorted(PENDING.glob("*.json"))
