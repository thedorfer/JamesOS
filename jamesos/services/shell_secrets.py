from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jamesos.config import VAULT


SUPPORTED_PROVIDERS = {"printify": "PRINTIFY_API_KEY", "etsy": "ETSY_API_KEY"}


class ShellSecretStore:
    """Small allowlisted private store; secret values never leave this class."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (VAULT / "JamesOS" / "secrets.env")

    def _provider(self, provider: str) -> str:
        value = str(provider).lower()
        if value not in SUPPORTED_PROVIDERS:
            raise ValueError("Unsupported provider")
        return value

    def _read(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        values = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                if key in SUPPORTED_PROVIDERS.values():
                    values[key] = value
        return values

    def status(self) -> list[dict[str, object]]:
        values = self._read()
        updated = datetime.fromtimestamp(self.path.stat().st_mtime, timezone.utc).isoformat() if self.path.exists() else None
        return [{"provider": p, "configured": bool(values.get(key)), "last_updated": updated} for p, key in SUPPORTED_PROVIDERS.items()]

    def save(self, provider: str, secret: str) -> dict[str, object]:
        provider = self._provider(provider)
        secret = str(secret)
        if not secret:
            return next(x for x in self.status() if x["provider"] == provider)
        if len(secret) > 4096 or re.search(r"[\r\n\x00]", secret):
            raise ValueError("Credential format is invalid")
        values = self._read(); values[SUPPORTED_PROVIDERS[provider]] = secret
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".secrets-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key in SUPPORTED_PROVIDERS.values():
                    if key in values:
                        handle.write(f"{key}={values[key]}\n")
                handle.flush(); os.fsync(handle.fileno())
            os.chmod(temporary, 0o600); os.replace(temporary, self.path); os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return next(x for x in self.status() if x["provider"] == provider)

    def _write_values(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".secrets-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key in SUPPORTED_PROVIDERS.values():
                    if key in values: handle.write(f"{key}={values[key]}\n")
                handle.flush(); os.fsync(handle.fileno())
            os.chmod(temporary, 0o600); os.replace(temporary, self.path); os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def delete(self, provider: str, *, confirmed: bool) -> dict[str, object]:
        provider = self._provider(provider)
        if not confirmed:
            raise PermissionError("Destructive confirmation required")
        values = self._read(); values.pop(SUPPORTED_PROVIDERS[provider], None)
        self._write_values(values)
        return next(x for x in self.status() if x["provider"] == provider)
