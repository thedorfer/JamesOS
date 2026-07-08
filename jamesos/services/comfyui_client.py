from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://127.0.0.1:8188"


class ComfyUIHTTPError(RuntimeError):
    def __init__(self, message: str, status_code: int, response_body: str, response_json: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.response_json = response_json


def _decode_body(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return None


def _http_error(exc: HTTPError, context: str) -> ComfyUIHTTPError:
    body = _decode_body(exc.read() or b"")
    response_json = _parse_json(body)
    return ComfyUIHTTPError(
        f"{context} failed with HTTP {exc.code}",
        int(exc.code),
        body,
        response_json,
    )


def _safe_url(api_url: str = DEFAULT_API_URL) -> str:
    parsed = urlparse(api_url.rstrip("/"))
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("ComfyUI API URL must be local-only: http://127.0.0.1:8188")
    if parsed.port != 8188:
        raise ValueError("ComfyUI API URL must use local ComfyUI port 8188")
    return api_url.rstrip("/")


def system_stats(api_url: str = DEFAULT_API_URL, timeout: float = 1.0) -> dict[str, Any]:
    try:
        url = f"{_safe_url(api_url)}/system_stats"
        with urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        return {
            "status": "ok",
            "api_url": _safe_url(api_url),
            "system_stats": json.loads(body or "{}"),
            "execution_enabled": False,
        }
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return {
            "status": "not_running",
            "api_url": api_url.rstrip("/"),
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


def queue_prompt(workflow_json: dict[str, Any], api_url: str = DEFAULT_API_URL, timeout: float = 10.0) -> dict[str, Any]:
    url = f"{_safe_url(api_url)}/prompt"
    body = json.dumps({"prompt": workflow_json}).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            data = json.loads(_decode_body(raw) or "{}")
    except HTTPError as exc:
        raise _http_error(exc, "ComfyUI prompt queue") from exc
    return {
        "status": "queued",
        "prompt_id": data.get("prompt_id"),
        "response": data,
        "execution_enabled": True,
        "api_url": _safe_url(api_url),
    }


def get_history(prompt_id: str, api_url: str = DEFAULT_API_URL, timeout: float = 10.0) -> dict[str, Any]:
    url = f"{_safe_url(api_url)}/history/{prompt_id}"
    try:
        with urlopen(url, timeout=timeout) as response:
            data = json.loads(_decode_body(response.read()) or "{}")
    except HTTPError as exc:
        raise _http_error(exc, "ComfyUI history request") from exc
    return {"status": "ok", "prompt_id": prompt_id, "history": data, "api_url": _safe_url(api_url)}


def wait_for_completion(prompt_id: str, timeout_seconds: int = 300, api_url: str = DEFAULT_API_URL) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_history: dict[str, Any] = {}
    while time.time() < deadline:
        history = get_history(prompt_id, api_url=api_url)
        last_history = history
        data = history.get("history", {})
        item = data.get(prompt_id) if isinstance(data, dict) else None
        if item and item.get("outputs"):
            return {"status": "completed", "prompt_id": prompt_id, "history": data, "api_url": _safe_url(api_url)}
        time.sleep(1)
    return {"status": "timeout", "prompt_id": prompt_id, "history": last_history.get("history", {}), "api_url": _safe_url(api_url)}


def get_output_images(prompt_id: str, api_url: str = DEFAULT_API_URL, timeout: float = 30.0) -> list[dict[str, Any]]:
    history = get_history(prompt_id, api_url=api_url, timeout=timeout)["history"]
    item = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    images: list[dict[str, Any]] = []
    for output in (item.get("outputs") or {}).values():
        for image in output.get("images", []) if isinstance(output, dict) else []:
            filename = str(image.get("filename") or "")
            if not filename:
                continue
            query = urlencode({
                "filename": filename,
                "subfolder": str(image.get("subfolder") or ""),
                "type": str(image.get("type") or "output"),
            })
            view_url = f"{_safe_url(api_url)}/view?{query}"
            try:
                with urlopen(view_url, timeout=timeout) as response:
                    content = response.read()
            except HTTPError as exc:
                raise _http_error(exc, "ComfyUI image download") from exc
            images.append({
                "filename": filename,
                "content": content,
                "metadata": image,
            })
    return images


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

    def queue_prompt(self, workflow_json: dict[str, Any]) -> dict[str, Any]:
        return queue_prompt(workflow_json, self.api_url)

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        return get_history(prompt_id, self.api_url)

    def wait_for_completion(self, prompt_id: str, timeout_seconds: int = 300) -> dict[str, Any]:
        return wait_for_completion(prompt_id, timeout_seconds, self.api_url)

    def get_output_images(self, prompt_id: str) -> list[dict[str, Any]]:
        return get_output_images(prompt_id, self.api_url)
