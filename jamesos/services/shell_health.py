from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from jamesos.config import VAULT
from jamesos.services.comfyui_client import health as comfyui_health
from jamesos.services.ollama_service import ollama_readiness


def calculate_shell_health(systems: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce bounded subsystem evidence to the shell's three safe states."""
    if any(item.get("required") and item.get("status") != "healthy" for item in systems):
        state = "red"
    elif any(item.get("status") != "healthy" for item in systems):
        state = "yellow"
    else:
        state = "green"
    labels = {
        "green": "All required local systems are healthy",
        "yellow": "JamesOS is usable; an optional subsystem is degraded",
        "red": "A required local subsystem is unavailable",
    }
    return {"state": state, "label": labels[state], "systems": systems}


class ShellHealthService:
    """Read-only local readiness checks. General health never contacts providers."""

    def __init__(
        self,
        *,
        storage: Path = VAULT,
        ollama_probe: Callable[[], dict[str, Any]] = ollama_readiness,
        image_probe: Callable[[], dict[str, Any]] = comfyui_health,
    ) -> None:
        self.storage = storage
        self.ollama_probe = ollama_probe
        self.image_probe = image_probe

    @staticmethod
    def _probe(probe: Callable[[], dict[str, Any]]) -> tuple[bool, str]:
        try:
            value = probe() or {}
            ready = bool(value.get("ready", value.get("ok", value.get("running", value.get("status") in {"ok", "healthy", "ready", "running"}))))
            return ready, "Ready" if ready else str(value.get("message") or value.get("error") or "Unavailable")[:240]
        except Exception as exc:
            return False, f"Unavailable ({type(exc).__name__})"

    def status(self, profiles: list[dict[str, Any]]) -> dict[str, Any]:
        ollama_ok, ollama_message = self._probe(self.ollama_probe)
        image_ok, image_message = self._probe(self.image_probe)
        storage_ok = self.storage.is_dir() and os.access(self.storage, os.R_OK | os.W_OK)
        profile_ok = bool(profiles) and all(
            (item.get("configuration") or {}).get("printify_shop_id")
            and (item.get("configuration") or {}).get("etsy_shop_slug")
            for item in profiles
        )
        gpu_ok = Path("/dev/nvidia0").exists() or Path("/proc/driver/nvidia/version").exists()
        systems = [
            {"id": "api", "label": "API/server", "status": "healthy", "required": True, "message": "Serving locally"},
            {"id": "ollama", "label": "Ollama", "status": "healthy" if ollama_ok else "unavailable", "required": True, "message": ollama_message},
            {"id": "gpu", "label": "GPU", "status": "healthy" if gpu_ok else "degraded", "required": False, "message": "Detected" if gpu_ok else "Not detected"},
            {"id": "comfyui", "label": "ComfyUI/image worker", "status": "healthy" if image_ok else "degraded", "required": False, "message": image_message},
            {"id": "storage", "label": "Private JamesOSData storage", "status": "healthy" if storage_ok else "unavailable", "required": True, "message": "Readable and writable" if storage_ok else "Inaccessible"},
            {"id": "commerce_profiles", "label": "Commerce-profile readiness", "status": "healthy" if profile_ok else "unavailable", "required": True, "message": "Configured" if profile_ok else "No safe enabled destination"},
        ]
        return calculate_shell_health(systems)
