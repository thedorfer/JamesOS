from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_API_URL = "http://127.0.0.1:8188"


def _safe_url(api_url: str = DEFAULT_API_URL) -> str:
    return api_url.rstrip("/")


def system_stats(api_url: str = DEFAULT_API_URL, timeout: float = 1.0) -> dict[str, Any]:
    url = f"{_safe_url(api_url)}/system_stats"
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {
            "status": "ok",
            "api_url": _safe_url(api_url),
            "system_stats": json.loads(body or "{}"),
            "execution_enabled": False,
        }
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "not_running",
            "api_url": _safe_url(api_url),
            "error": str(exc),
            "system_stats": {},
            "execution_enabled": False,
        }


def is_running(api_url: str = DEFAULT_API_URL, timeout: float = 1.0) -> bool:
    return system_stats(api_url, timeout=timeout).get("status") == "ok"


def detect_install_path() -> dict[str, Any]:
    from pathlib import Path

    preferred = Path.home() / "AI" / "ComfyUI"
    legacy = Path.home() / "ComfyUI"
    if preferred.exists():
        return {"path": str(preferred), "exists": True, "kind": "preferred"}
    if legacy.exists():
        return {"path": str(legacy), "exists": True, "kind": "legacy"}
    return {"path": str(preferred), "exists": False, "kind": "preferred"}


def health(api_url: str = DEFAULT_API_URL, timeout: float = 1.0) -> dict[str, Any]:
    stats = system_stats(api_url, timeout=timeout)
    return {
        "status": "running" if stats.get("status") == "ok" else "not_running",
        "provider": "comfyui",
        "api_url": _safe_url(api_url),
        "running": stats.get("status") == "ok",
        "install_path": detect_install_path(),
        "execution_enabled": False,
        "prompt_queue_enabled": False,
        "one_image_job_at_a_time": True,
        "system_stats": stats.get("system_stats", {}),
        "message": "Health check only. JamesOS does not execute ComfyUI workflows in this phase.",
    }


class ComfyUIClient:
    def __init__(self, api_url: str = DEFAULT_API_URL) -> None:
        self.api_url = api_url

    def health(self) -> dict[str, Any]:
        return health(self.api_url)

    def status(self) -> dict[str, Any]:
        return self.health()

    def system_stats(self) -> dict[str, Any]:
        return system_stats(self.api_url)

    def is_running(self) -> bool:
        return is_running(self.api_url)
