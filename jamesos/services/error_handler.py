from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import traceback
from typing import Any
from uuid import uuid4

from jamesos.config import VAULT
from jamesos.core.errors import JamesOSError, unexpected_error
from jamesos.core.structured_logging import error_logger, redact


DIAGNOSTIC_ROOT = VAULT / "JamesOS" / "Diagnostics" / "errors"
CATEGORY_HTTP_STATUS = {"configuration": 500, "validation": 422, "approval": 409, "artifact": 409, "state": 409,
                        "authentication": 502, "authorization": 502, "font_acquisition": 422, "printify": 502,
                        "external_dependency": 503, "comfyui": 503, "filesystem": 500, "internal": 500}


def new_error_id(now: datetime | None = None) -> str:
    return f"err-{(now or datetime.now().astimezone()).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _causes(error: BaseException, limit: int = 8) -> list[dict[str, str]]:
    result = []; current: BaseException | None = error
    while current is not None and len(result) < limit:
        result.append({"type": type(current).__name__, "message": str(current)[:2000]})
        current = current.__cause__ or current.__context__ or getattr(current, "original_cause", None)
    return result


def build_envelope(error: JamesOSError, *, error_id: str | None = None, request_id: str | None = None,
                   diagnostic_path: str | None = None, debug: bool = False) -> dict[str, Any]:
    context = redact(error.context); state = redact(error.state)
    envelope = {"error_id": error_id or new_error_id(), "code": error.code, "category": error.category,
        "severity": error.severity, "occurred_at": datetime.now().astimezone().isoformat(), "operation": error.operation,
        "stage": error.stage, "job_id": context.get("job_id"), "run_id": context.get("run_id"),
        "request_id": request_id or context.get("request_id"), "composition_id": context.get("composition_id"),
        "printify_product_id": context.get("printify_product_id"), "retryable": error.retryable,
        "user_message": error.user_message, "diagnostic_message": error.diagnostic_message,
        "suggested_action": error.suggested_action, "context": context, "state": state,
        "cause_chain": _causes(error), "diagnostic_artifact_path": diagnostic_path}
    if debug: envelope["traceback"] = "".join(traceback.format_exception(error))[-12000:]
    return redact(envelope)


def _persist(envelope: dict[str, Any], root: Path) -> Path:
    day = str(envelope["occurred_at"])[:10]; destination = root / day / f"{envelope['error_id']}.json"
    envelope["diagnostic_artifact_path"] = str(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(envelope, handle, indent=2, sort_keys=True); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        if destination.exists(): raise FileExistsError(destination)
        os.link(temporary, destination); temporary.unlink()
    finally:
        if temporary.exists(): temporary.unlink()
    return destination


def handle_error(exc: BaseException, *, operation: str, stage: str = "boundary", context: dict[str, Any] | None = None,
                 state: dict[str, Any] | None = None, request_id: str | None = None, diagnostic_root: Path = DIAGNOSTIC_ROOT,
                 persist: bool = True, log: bool = True, debug: bool = False) -> dict[str, Any]:
    error = exc if isinstance(exc, JamesOSError) else unexpected_error(exc, operation=operation, stage=stage, context=context, state=state)
    if context: error.context.update(context)
    if state: error.state.update(state)
    envelope = build_envelope(error, request_id=request_id, debug=debug); path = None
    if persist:
        try:
            path = _persist(envelope, diagnostic_root); envelope["diagnostic_artifact_path"] = str(path)
        except Exception as persistence_error:
            envelope["diagnostic_artifact_path"] = None
            if log: error_logger().warning("diagnostic persistence failed", extra={"structured": {"event": "diagnostic_persistence_failed",
                "error_id": envelope["error_id"], "warning": type(persistence_error).__name__}})
    if log:
        error_logger().error(error.user_message, extra={"structured": {"error_id": envelope["error_id"], "code": error.code,
            "severity": error.severity, "operation": error.operation, "stage": error.stage, "job_id": envelope.get("job_id"),
            "run_id": envelope.get("run_id"), "retryable": error.retryable, "message": error.user_message}})
    return envelope


def cli_error(envelope: dict[str, Any]) -> dict[str, Any]:
    return {"result": "failed", "error_id": envelope["error_id"], "code": envelope["code"],
        "user_message": envelope["user_message"], "retryable": envelope["retryable"],
        "suggested_action": envelope["suggested_action"], "state": envelope["state"],
        "diagnostic_path": envelope.get("diagnostic_artifact_path")}


def api_error(envelope: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status = CATEGORY_HTTP_STATUS.get(str(envelope["category"]), 500)
    return status, {"error_id": envelope["error_id"], "code": envelope["code"], "message": envelope["user_message"],
                    "retryable": envelope["retryable"], "suggested_action": envelope["suggested_action"]}
