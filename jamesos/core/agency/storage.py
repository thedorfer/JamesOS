from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class AgencyStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "agents": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        _reject_secrets(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _reject_secrets(value: Any, key: str = "", handles_only: bool = False) -> None:
    forbidden = ("password", "token", "api_key", "secret_value", "private_key")
    if any(item in key.lower() for item in forbidden) and not handles_only and key.lower() not in {"secret_handles", "secret_grants"}:
        raise ValueError("Agency state cannot contain secret values")
    if isinstance(value, dict):
        for child_key, child in value.items():
            _reject_secrets(child, str(child_key), handles_only or key.lower() in {"secret_handles", "secret_grants"})
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_secrets(child, key, handles_only)
