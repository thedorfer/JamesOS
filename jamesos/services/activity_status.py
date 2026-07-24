"""Durable, application-wide activity aggregation for the JamesOS shell."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from jamesos.config import VAULT
from jamesos.services.coloring_book_producer import ColoringBookProducer
from jamesos.services.product_orchestrator import ROOT as COMMERCE_ROOT


ACTIVE = {"previewed", "submission_started", "retry_submission_started", "running", "queued", "outputs_received"}
PROVIDER_ACTIVE = {"provider_submitted"}
APPROVAL = {"waiting", "waiting_for_approval", "waiting for approval", "pending_approval", "awaiting_human_approval", "awaiting_final_approval"}
ATTENTION = {"retry_authorized", "remaining_samples_authorized", "provider_submission_lost_after_restart", "reconciliation_required", "paused", "manual_verification_required"}
FAILED = {"failed", "generation_failed", "revision_failed"}
COMPLETE = {"completed", "review_ready", "sample_style_approved", "published", "canceled"}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _elapsed(started: Any, now: datetime) -> int:
    try:
        return max(0, int((now - datetime.fromisoformat(str(started))).total_seconds()))
    except (TypeError, ValueError):
        return 0


class ActivityStatusService:
    """Projects durable shared workflow records into one read-only shell view."""

    def __init__(
        self,
        *,
        projects_root: Path | None = None,
        commerce_root: Path | None = None,
        agency_runs_root: Path | None = None,
        producer_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.projects_root = projects_root or VAULT / "JamesOS" / "Books" / "Projects"
        self.commerce_root = commerce_root or COMMERCE_ROOT
        self.agency_runs_root = agency_runs_root or VAULT / "JamesOS" / "Agency" / "runs"
        self.producer_factory = producer_factory or ColoringBookProducer
        self.clock = clock or (lambda: datetime.now().astimezone())

    def status(self) -> dict[str, Any]:
        now = self.clock()
        items = self._producer_items(now) + self._commerce_items(now) + self._agency_items(now)
        # De-duplicate a durable operation exposed by more than one shared index.
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for item in items:
            key = (item["agent_capability_id"], item.get("project_id") or item.get("job_id") or "", item["operation_type"])
            previous = unique.get(key)
            if previous is None or str(item.get("last_update_timestamp") or "") > str(previous.get("last_update_timestamp") or ""):
                unique[key] = item
        items = list(unique.values())
        order = {"Working": 0, "Waiting for approval": 1, "Needs attention": 2, "Failed": 3, "Completed": 4}
        items.sort(key=lambda x: (order.get(x["state"], 9), -self._epoch(x.get("last_update_timestamp"))))
        active = [x for x in items if x["state"] == "Working"]
        waits = [x for x in items if x["state"] == "Waiting for approval"]
        attention = [x for x in items if x["state"] == "Needs attention"]
        failures = [x for x in items if x["state"] == "Failed"]
        recent = next((x for x in items if x["state"] == "Completed"), None)
        visible = active + waits + attention + failures + ([recent] if recent else [])
        if active:
            state, label = "Working", f"Working: {active[0]['display_label']}"
        elif waits:
            state, label = "Waiting for approval", "Waiting for approval"
        elif attention:
            state, label = "Needs attention", "Needs attention"
        elif failures:
            state, label = "Failed", "Failed"
        else:
            state, label = "Idle", "Idle"
        unresolved = bool(active or waits or attention or failures)
        return {
            "state": state,
            "display_label": label,
            "items": visible,
            "counts": {"working": len(active), "waiting_for_approval": len(waits), "needs_attention": len(attention), "failed": len(failures)},
            "has_unresolved_activity": unresolved,
            "poll_interval_ms": 3000 if unresolved else 15000,
            "generated_at": now.isoformat(),
        }

    @staticmethod
    def _epoch(value: Any) -> float:
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return 0

    def _item(self, *, state: str, operation: str, capability: str, label: str, workspace: str,
              stage: str, started: Any, updated: Any, now: datetime, project_id: str = "",
              job_id: str = "", current: Any = None, expected: Any = None, approval: bool = False,
              failure: Any = None) -> dict[str, Any]:
        return {
            "state": state, "operation_type": operation, "agent_capability_id": capability,
            "display_label": label, "project_id": project_id or None, "job_id": job_id or None,
            "workspace_url": workspace, "operation_state": stage, "started_timestamp": started,
            "elapsed_seconds": _elapsed(started, now), "progress_current": current,
            "progress_expected": expected, "approval_required": approval,
            "safe_failure_message": failure, "last_update_timestamp": updated or started,
        }

    def _producer_items(self, now: datetime) -> list[dict[str, Any]]:
        result = []
        if not self.projects_root.is_dir():
            return result
        producer = None
        for root in self.projects_root.iterdir():
            journal = _read(root / "samples" / "operations.json").get("operations") or []
            manifest = _read(root / "samples" / "manifest.json")
            if not journal and not manifest:
                continue
            latest = next((x for x in reversed(journal) if isinstance(x, dict) and x.get("state")), {})
            stage = str(latest.get("state") or manifest.get("operation_state") or manifest.get("status") or "")
            status = None
            if latest.get("operation") == "regenerate_single_page" or stage in ACTIVE | PROVIDER_ACTIVE:
                try:
                    producer = producer or self.producer_factory()
                    status = producer.sample_status(root.name)
                    progress = status.get("progress") or {}
                    stage = str(progress.get("operation_state") or status.get("operation_state") or stage)
                    # A prompt id by itself is not proof that the provider is still working.
                    if stage in PROVIDER_ACTIVE and not progress.get("provider_state_confirmed"):
                        stage = "reconciliation_required"
                except Exception:
                    stage = "reconciliation_required"
            progress = (status or {}).get("progress") or manifest.get("progress") or {}
            if stage in ACTIVE or (stage in PROVIDER_ACTIVE and progress.get("provider_state_confirmed")):
                state = "Working"
            elif stage in ATTENTION:
                state = "Needs attention"
            elif stage in FAILED:
                state = "Failed"
            elif stage in COMPLETE:
                state = "Completed"
            else:
                continue
            pages = progress.get("page_ids") or manifest.get("retry_page_ids") or manifest.get("selected_page_ids") or latest.get("page_ids") or ([latest.get("page_id")] if latest.get("page_id") else [])
            operation = str(progress.get("operation_type") or latest.get("operation") or "sample_generation")
            verb = "Regenerating" if "regenerate" in operation else "Generating"
            label = f"{verb} {', '.join(pages)}" if pages else "Preparing sample pages"
            failure = progress.get("safe_failure_message") or manifest.get("safe_failure_message") or latest.get("safe_failure_message")
            result.append(self._item(state=state, operation=operation, capability="jamesos.coloring-book-producer",
                label=label, project_id=root.name, workspace=f"/app?view=agency.coloring-book-producer&project_id={quote(root.name)}&producer_tab=samples",
                stage=stage, started=progress.get("started_at") or latest.get("timestamp"), updated=progress.get("last_status_update_at") or latest.get("timestamp"),
                now=now, current=progress.get("operation_artifact_count", manifest.get("artifact_count")), expected=progress.get("expected_artifact_count") or len(pages),
                approval=stage in ATTENTION, failure=failure))
        return result

    def _commerce_items(self, now: datetime) -> list[dict[str, Any]]:
        result = []
        if not self.commerce_root.is_dir():
            return result
        for path in self.commerce_root.glob("*/orchestrator-state.json"):
            value = _read(path)
            stage = str(value.get("stage") or value.get("status") or "")
            if stage in APPROVAL or (stage.startswith("awaiting_") and stage.endswith("_confirmation")):
                state = "Waiting for approval"
            elif stage in FAILED:
                state = "Failed"
            elif stage in ATTENTION:
                state = "Needs attention"
            elif stage in COMPLETE:
                state = "Completed"
            elif stage:
                state = "Working"
            else:
                continue
            job = str(value.get("job_id") or path.parent.name)
            failure = (value.get("generation_failure") or {}).get("safe_message") or value.get("failure_message_safe") or value.get("last_error")
            if isinstance(failure, dict): failure = failure.get("user_message") or failure.get("safe_message") or "The operation failed safely."
            updated = value.get("updated_at") or value.get("completed_at") or value.get("started_at")
            result.append(self._item(state=state, operation=str(value.get("operation") or "commerce_job"), capability="merchant",
                label=str(value.get("progress_label") or stage).replace("_", " ").capitalize(), job_id=job,
                workspace=f"/app?view=commerce.review&job_id={quote(job)}", stage=stage,
                started=value.get("started_at") or value.get("created_at"), updated=updated, now=now,
                approval=state == "Waiting for approval", failure=str(failure) if failure else None))
        return result

    def _agency_items(self, now: datetime) -> list[dict[str, Any]]:
        result = []
        if not self.agency_runs_root.is_dir():
            return result
        paths = list(self.agency_runs_root.glob("*.json")) + list(self.agency_runs_root.glob("*/state.json"))
        for path in paths:
            value = _read(path)
            stage = str(value.get("state") or value.get("status") or value.get("stage") or "").lower()
            if stage in APPROVAL:
                state = "Waiting for approval"
            elif stage in FAILED:
                state = "Failed"
            elif stage in ATTENTION:
                state = "Needs attention"
            elif stage in COMPLETE:
                state = "Completed"
            elif stage in {"running", "queued"}:
                state = "Working"
            else:
                continue
            run = str(value.get("run_id") or value.get("job_id") or path.stem)
            capability = str(value.get("agent_id") or value.get("capability_id") or "agent-os")
            view = str(value.get("workspace_view") or "agency.home")
            workspace = str(value.get("workspace_url") or f"/app?view={quote(view)}&run_id={quote(run)}")
            result.append(self._item(state=state, operation=str(value.get("operation") or value.get("type") or "agent_run"),
                capability=capability, label=str(value.get("display_label") or value.get("operation") or "Agent OS run"),
                job_id=run, workspace=workspace, stage=stage, started=value.get("started_at"), updated=value.get("updated_at") or value.get("completed_at"),
                now=now, approval=state == "Waiting for approval", failure=value.get("safe_failure_message")))
        return result
