from __future__ import annotations

from typing import Any, Callable

from jamesos.services.shell_health import ShellHealthService


class ShellDashboardService:
    """Build a bounded, read-only dashboard without making provider requests."""

    def __init__(self, *, health: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
                 jobs: Callable[[], list[dict[str, Any]]] | None = None) -> None:
        self.health = health or (lambda profiles: ShellHealthService().status(profiles))
        self.jobs = jobs or (lambda: [])

    def status(self, profiles: list[dict[str, Any]]) -> dict[str, Any]:
        health = self.health(profiles)
        try:
            source = self.jobs()
        except Exception:
            source = []
        jobs = []
        for item in source[:25]:
            status = str(item.get("status") or "unknown")
            jobs.append({
                "job_id": str(item.get("job_id") or "")[:80],
                "kind": str(item.get("type") or "job")[:80],
                "status": status[:40],
                "updated_at": str(item.get("updated_at") or "")[:80],
                "destination": str((item.get("payload") or {}).get("destination_name") or "Unpublished workspace")[:120],
                "publication_state": "not_published",
                "order_state": "not_created",
            })
        return {
            "summary": {"state": health.get("state", "yellow"), "label": health.get("label", "Status available")},
            "systems": health.get("systems", []),
            "work": {
                "active": [j for j in jobs if j["status"] in {"pending", "approved", "running"}],
                "failed": [j for j in jobs if j["status"] == "failed"],
                "ready": [j for j in jobs if j["status"] in {"completed", "ready_for_review"}],
                "pending_confirmations": sum(1 for j in source if j.get("requires_approval") and not j.get("approved")),
                "agency_runs": 0,
            },
            "recent_results": [j for j in jobs if j["status"] in {"completed", "failed"}][:8],
        }
