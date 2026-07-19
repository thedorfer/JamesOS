from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import secrets
import threading
import time
from typing import Any

from jamesos.config import JAMESOS_DATA
from jamesos.services.product_orchestrator import _atomic_json


POLICY_PATH = JAMESOS_DATA / "JamesOS" / "ApplicationShell" / "private-chat-policy.json"
AUDIT_PATH = JAMESOS_DATA / "JamesOS" / "ApplicationShell" / "admin-audit.json"
AFFIRMATION_TTL_SECONDS = 60 * 60
_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


class PrivateChatPolicy:
    def __init__(self, path: Path | None = None, audit_path: Path | None = None):
        self.path = path or POLICY_PATH
        self.audit_path = audit_path or AUDIT_PATH

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"adult_mode_available": False}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"adult_mode_available": False}
        return {"adult_mode_available": value.get("adult_mode_available") is True}

    def revision(self) -> str:
        return sha256(json.dumps(self._read(), sort_keys=True).encode()).hexdigest()

    def status(self) -> dict[str, Any]:
        return {**self._read(), "revision": self.revision()}

    def save(self, *, available: Any, revision: str) -> dict[str, Any]:
        if not isinstance(available, bool):
            raise ValueError("Adult-mode availability must be a boolean.")
        if not secrets.compare_digest(str(revision), self.revision()):
            raise ValueError("Private-chat policy changed; refresh before saving.")
        _atomic_json(self.path, {"adult_mode_available": available})
        events: list[dict[str, Any]] = []
        if self.audit_path.is_file():
            try: events = json.loads(self.audit_path.read_text(encoding="utf-8"))
            except (OSError, ValueError): events = []
        events.append({"timestamp": datetime.now().astimezone().isoformat(), "event": "adult_mode_availability_updated", "enabled": available})
        _atomic_json(self.audit_path, events[-200:])
        return self.status()


def affirm_adult_session(*, now: float | None = None, ttl_seconds: int = AFFIRMATION_TTL_SECONDS) -> dict[str, Any]:
    created = time.time() if now is None else now
    session_id = secrets.token_urlsafe(32)
    record = {"affirmed": True, "created_at": created, "expires_at": created + ttl_seconds}
    with _LOCK:
        _SESSIONS[session_id] = record
    return {"adult_consent_session": session_id, "expires_at": record["expires_at"]}


def validate_adult_session(session_id: Any, *, now: float | None = None) -> bool:
    if not isinstance(session_id, str) or len(session_id) < 32:
        return False
    current = time.time() if now is None else now
    with _LOCK:
        record = _SESSIONS.get(session_id)
        if not record or record["expires_at"] <= current:
            _SESSIONS.pop(session_id, None)
            return False
        return record.get("affirmed") is True


def end_adult_session(session_id: Any) -> None:
    if isinstance(session_id, str):
        with _LOCK:
            _SESSIONS.pop(session_id, None)


def clear_sessions() -> None:
    """Test helper; session records contain no conversation content."""
    with _LOCK:
        _SESSIONS.clear()
