from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT


QUEUE_ROOT = VAULT / "JamesOS" / "Queue"
PENDING = QUEUE_ROOT / "pending"
IN_PROGRESS = QUEUE_ROOT / "in_progress"
PROCESSED = QUEUE_ROOT / "processed"
FAILED = QUEUE_ROOT / "failed"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Job Queue.md"

COMPLETED_STATUSES = {"processed"}


class JobQueueError(ValueError):
    pass


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def status_dirs() -> dict[str, Path]:
    return {
        "pending": PENDING,
        "in_progress": IN_PROGRESS,
        "processed": PROCESSED,
        "failed": FAILED,
    }


def ensure_job_queue_dirs() -> None:
    for folder in status_dirs().values():
        folder.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str, status: str) -> Path:
    folder = status_dirs().get(status)
    if folder is None:
        raise JobQueueError(f"Unknown job status: {status}")
    return folder / f"{job_id}.json"


def _find_job_path(job_id: str) -> Path | None:
    ensure_job_queue_dirs()
    for folder in status_dirs().values():
        path = folder / f"{job_id}.json"
        if path.exists():
            return path
    return None


def _read_job(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return normalize_job(raw, path)


def normalize_job(job: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    timestamp = str(job.get("created_at") or now_timestamp())
    job_id = str(job.get("job_id") or job.get("id") or (path.stem if path else uuid.uuid4().hex))
    job.setdefault("id", job_id)
    job["job_id"] = job_id
    job.setdefault("type", "unknown")
    job.setdefault("status", path.parent.name if path else "pending")
    job.setdefault("created_at", timestamp)
    job.setdefault("updated_at", timestamp)
    job.setdefault("priority", 5)
    job.setdefault("requires_approval", False)
    job.setdefault("approved", not bool(job.get("requires_approval")))
    job.setdefault("payload", {})
    job.setdefault("steps", [])
    job.setdefault("logs", [])
    return job


def _write_job(job: dict[str, Any]) -> Path:
    ensure_job_queue_dirs()
    status = job.get("status", "pending")
    path = _job_path(job["job_id"], status)
    path.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
    write_job_queue_report()
    return path


def _move_job(job: dict[str, Any], old_path: Path, new_status: str) -> Path:
    if new_status not in status_dirs():
        raise JobQueueError(f"Unknown job status: {new_status}")
    if new_status in COMPLETED_STATUSES and job.get("requires_approval") and not job.get("approved"):
        raise JobQueueError("Approval-gated jobs cannot complete until approved")

    old_status = job.get("status", "pending")
    job["status"] = new_status
    job["updated_at"] = now_timestamp()
    job.setdefault("logs", []).append({
        "created_at": job["updated_at"],
        "message": f"Status changed from {old_status} to {new_status}",
    })

    new_path = _job_path(job["job_id"], new_status)
    new_path.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
    if old_path != new_path and old_path.exists():
        old_path.unlink()
    write_job_queue_report()
    return new_path


def create_job(
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 5,
    requires_approval: bool = True,
    steps: list[dict[str, Any]] | list[str] | None = None,
) -> dict[str, Any]:
    ensure_job_queue_dirs()
    timestamp = now_timestamp()
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    normalized_steps = []
    for step in steps or []:
        if isinstance(step, str):
            normalized_steps.append({"name": step, "status": "pending", "updated_at": timestamp})
        else:
            normalized_steps.append({
                "name": str(step.get("name", "step")),
                "status": str(step.get("status", "pending")),
                "updated_at": str(step.get("updated_at", timestamp)),
            })

    job = {
        "job_id": job_id,
        "type": job_type,
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
        "priority": priority,
        "requires_approval": requires_approval,
        "approved": False,
        "payload": payload or {},
        "steps": normalized_steps,
        "logs": [{"created_at": timestamp, "message": "Job created"}],
    }
    _write_job(job)
    return job


def list_jobs(status: str | None = None) -> list[dict[str, Any]]:
    ensure_job_queue_dirs()
    dirs = status_dirs()
    statuses = [status] if status else list(dirs)
    jobs: list[dict[str, Any]] = []
    for item_status in statuses:
        folder = dirs.get(item_status)
        if folder is None:
            raise JobQueueError(f"Unknown job status: {item_status}")
        for path in sorted(folder.glob("*.json")):
            jobs.append(_read_job(path))
    return sorted(
        jobs,
        key=lambda job: (int(job.get("priority", 5)), str(job.get("created_at", ""))),
    )


def get_job(job_id: str) -> dict[str, Any]:
    path = _find_job_path(job_id)
    if path is None:
        raise JobQueueError(f"Job not found: {job_id}")
    return _read_job(path)


def update_job_status(job_id: str, status: str) -> dict[str, Any]:
    path = _find_job_path(job_id)
    if path is None:
        raise JobQueueError(f"Job not found: {job_id}")
    job = _read_job(path)
    _move_job(job, path, status)
    return get_job(job_id)


def append_job_log(job_id: str, message: str) -> dict[str, Any]:
    path = _find_job_path(job_id)
    if path is None:
        raise JobQueueError(f"Job not found: {job_id}")
    job = _read_job(path)
    timestamp = now_timestamp()
    job["updated_at"] = timestamp
    job.setdefault("logs", []).append({"created_at": timestamp, "message": message})
    _write_job(job)
    return job


def mark_step(job_id: str, step_name: str, status: str, note: str = "") -> dict[str, Any]:
    path = _find_job_path(job_id)
    if path is None:
        raise JobQueueError(f"Job not found: {job_id}")
    job = _read_job(path)
    timestamp = now_timestamp()
    steps = job.setdefault("steps", [])
    for step in steps:
        if step.get("name") == step_name:
            step["status"] = status
            step["updated_at"] = timestamp
            if note:
                step["note"] = note
            break
    else:
        step = {"name": step_name, "status": status, "updated_at": timestamp}
        if note:
            step["note"] = note
        steps.append(step)

    job["updated_at"] = timestamp
    job.setdefault("logs", []).append({
        "created_at": timestamp,
        "message": f"Step {step_name} marked {status}",
    })
    _write_job(job)
    return job


def approve_job(job_id: str, approved_by: str = "James") -> dict[str, Any]:
    path = _find_job_path(job_id)
    if path is None:
        raise JobQueueError(f"Job not found: {job_id}")
    job = _read_job(path)
    timestamp = now_timestamp()
    job["approved"] = True
    job["approved_at"] = timestamp
    job["approved_by"] = approved_by
    job["updated_at"] = timestamp
    job.setdefault("logs", []).append({
        "created_at": timestamp,
        "message": f"Approved by {approved_by}",
    })
    _write_job(job)
    return job


def fail_job(job_id: str, reason: str = "") -> dict[str, Any]:
    if reason:
        append_job_log(job_id, f"Failure reason: {reason}")
    return update_job_status(job_id, "failed")


def write_job_queue_report() -> str:
    ensure_job_queue_dirs()
    lines = [
        "# Job Queue",
        "",
        f"Updated: {now_timestamp()}",
        "",
    ]
    for status in ["pending", "in_progress", "processed", "failed"]:
        jobs = list_jobs(status)
        lines.extend([f"## {status.replace('_', ' ').title()}", ""])
        if not jobs:
            lines.extend(["- None", ""])
            continue
        for job in jobs[:50]:
            approval = "approved" if job.get("approved") else "needs approval"
            lines.append(
                f"- `{job.get('job_id')}` {job.get('type')} "
                f"(priority {job.get('priority')}, {approval})"
            )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return str(REPORT_PATH)
