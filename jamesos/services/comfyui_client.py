from __future__ import annotations

from typing import Any


class ComfyUIClient:
    def __init__(self, api_url: str = "http://localhost:8188") -> None:
        self.api_url = api_url

    def status(self) -> dict[str, Any]:
        return {
            "provider": "comfyui",
            "api_url": self.api_url,
            "status": "placeholder_only",
            "enabled": False,
            "message": "ComfyUI integration is planned for a later phase and is not called in Phase 1.",
        }

    def generate_image(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "message": "Image generation is disabled in Phase 1.",
        }
