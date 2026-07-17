from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from jamesos.core.agents.secrets import SecretProvider


class AgencySecretProvider(SecretProvider):
    """Adds write/list operations to the existing handle-based secret provider."""

    def __init__(self, root: Path):
        self.root = Path(root)
        handles = {}
        if self.root.exists():
            for path in self.root.glob("*.secret"):
                try:
                    handle = base64.urlsafe_b64decode(path.stem.encode("ascii")).decode("utf-8")
                except (ValueError, UnicodeError):
                    continue
                if handle.startswith("secret:"):
                    handles[handle] = path
        super().__init__(handles)

    def create(self, label: str, value: str) -> dict:
        if not isinstance(value, str) or not value:
            raise ValueError("secret value is required")
        safe = "".join(character for character in label.lower() if character.isalnum() or character in "-_").strip("-_")
        if not safe:
            raise ValueError("secret label is invalid")
        handle = f"secret:{safe}:{hashlib.sha256(os.urandom(16)).hexdigest()[:12]}"
        filename = base64.urlsafe_b64encode(handle.encode("utf-8")).decode("ascii")
        path = self.root / f"{filename}.secret"
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        self.handles[handle] = path
        return {"handle": handle, "label": label, "configured": True}

    def metadata(self, handle: str) -> dict:
        status = self.status(handle)
        return {"handle": handle, **status}
