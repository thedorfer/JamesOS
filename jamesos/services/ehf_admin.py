from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from jamesos.services.error_handler import DIAGNOSTIC_ROOT


ERROR_ID = re.compile(r"^err-[A-Za-z0-9-]{8,80}$")
SAFE_FIELDS = ("error_id", "severity", "code", "operation", "stage", "user_message", "retryable", "job_id", "run_id")


class EHFAdminService:
    """Bounded Admin projection over the existing EHF envelope persistence."""

    def __init__(self, root: Path = DIAGNOSTIC_ROOT, *, limit: int = 200) -> None:
        self.root = root
        self.limit = min(max(limit, 1), 500)

    @staticmethod
    def validate_id(error_id: str) -> str:
        if not ERROR_ID.fullmatch(str(error_id)):
            raise ValueError("Invalid error ID")
        return str(error_id)

    def _paths(self) -> list[Path]:
        if not self.root.is_dir(): return []
        return sorted(self.root.glob("????-??-??/err-*.json"), reverse=True)[: self.limit]

    def _load(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _safe(value: dict[str, Any]) -> dict[str, Any]:
        result = {key: value.get(key) for key in SAFE_FIELDS}
        result["timestamp"] = str(value.get("occurred_at") or "")[:40]
        result["message"] = str(value.get("user_message") or "An operation failed safely.")[:500]
        result.pop("user_message", None)
        admin = value.get("admin_state") if isinstance(value.get("admin_state"), dict) else {}
        result.update({"acknowledged": bool(admin.get("acknowledged")), "resolved": bool(admin.get("resolved"))})
        return result

    def records(self, filters: dict[str, str] | None = None) -> dict[str, Any]:
        filters = filters or {}; records = [self._safe(v) for p in self._paths() if (v := self._load(p))]
        def keep(item: dict[str, Any]) -> bool:
            exact = (("severity", "severity"), ("operation", "operation"), ("stage", "stage"), ("job", "job_id"))
            if any(filters.get(query) and str(item.get(field) or "") != filters[query] for query, field in exact): return False
            if filters.get("resolved") in {"true", "false"} and item["resolved"] != (filters["resolved"] == "true"): return False
            stamp = item["timestamp"][:10]
            return not ((filters.get("date_from") and stamp < filters["date_from"]) or (filters.get("date_to") and stamp > filters["date_to"]))
        records = [item for item in records if keep(item)]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        def recent(item: dict[str, Any]) -> bool:
            try:return datetime.fromisoformat(item["timestamp"]).astimezone(timezone.utc) >= cutoff
            except ValueError:return False
        summary = {
            "unresolved_errors": sum(not x["resolved"] for x in records),
            "warnings": sum(x["severity"] == "warning" for x in records),
            "critical_failures": sum(x["severity"] in {"critical", "fatal"} for x in records),
            "failed_commerce_jobs": len({x["job_id"] for x in records if x["job_id"] and str(x["operation"]).startswith("commerce")}),
            "recent_service_failures": sum(str(x["operation"]).startswith(("application", "service", "access", "attachment")) for x in records[:50]),
            "last_24_hours": sum(recent(x) for x in records),
        }
        return {"summary": summary, "records": records}

    def detail(self, error_id: str) -> dict[str, Any]:
        path, value = self._find(error_id); safe = self._safe(value)
        context = value.get("context") if isinstance(value.get("context"), dict) else {}
        state = value.get("state") if isinstance(value.get("state"), dict) else {}
        safe.update({
            "retry_guidance": str(value.get("suggested_action") or "Review the associated operation before retrying.")[:500],
            "provider_contacted": bool(state.get("provider_contacted", context.get("provider_contacted", False))),
            "draft_exists": bool(state.get("printify_draft_exists", context.get("printify_product_id"))),
            "publication_state": str(state.get("publication_status") or "not_published")[:40],
            "order_state": str(state.get("order_status") or "not_created")[:40],
            "validation_reasons": [str(x)[:300] for x in (state.get("validation_reasons") or [])[:20]],
            "stage_timeline": [{"stage": safe["stage"], "timestamp": safe["timestamp"], "result": "failed"}],
        })
        return safe

    def _find(self, error_id: str) -> tuple[Path, dict[str, Any]]:
        error_id = self.validate_id(error_id)
        for path in self._paths():
            if path.stem == error_id and (value := self._load(path)) is not None:return path, value
        raise LookupError("Error record not found")

    def update(self, error_id: str, *, action: str) -> dict[str, Any]:
        if action not in {"acknowledge", "resolve"}:raise ValueError("Unsupported EHF action")
        path, value = self._find(error_id); admin = value.setdefault("admin_state", {})
        now = datetime.now().astimezone().isoformat()
        if action == "acknowledge":admin.update(acknowledged=True, acknowledged_at=now)
        else:admin.update(acknowledged=True, resolved=True, resolved_at=now)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True);handle.write("\n");handle.flush();os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():temporary.unlink()
        return self._safe(value)

    def export(self, filters: dict[str, str] | None = None) -> dict[str, Any]:
        value = self.records(filters)
        return {"format": "jamesos-ehf-sanitized-v1", **value}
