from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = ("authorization", "token", "password", "secret", "cookie", "session", "private_key", "access_token", "refresh_token")
SENSITIVE_QUERY_KEYS = ("token", "key", "secret", "password", "signature", "auth", "session")


def _sensitive(key: object, patterns: tuple[str, ...]) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(pattern in normalized for pattern in patterns)


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https"): return value
        query = urlencode([(key, REDACTED if _sensitive(key, SENSITIVE_QUERY_KEYS) else item) for key, item in parse_qsl(parts.query, keep_blank_values=True)])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except ValueError:
        return value


def redact(value: Any, *, key: object = "", depth: int = 0) -> Any:
    if _sensitive(key, SENSITIVE_KEYS): return REDACTED
    if depth > 12: return "[TRUNCATED]"
    if isinstance(value, dict): return {str(k): redact(v, key=k, depth=depth + 1) for k, v in value.items() if str(k).lower() != "headers"}
    if isinstance(value, (list, tuple)): return [redact(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, bytes): return f"[BINARY {len(value)} bytes]"
    if isinstance(value, str):
        sanitized = sanitize_url(value)
        if sanitized != value: return sanitized[:2000]
        lowered = value.lower()
        if "bearer " in lowered: return REDACTED
        return value[:4000]
    if value is None or isinstance(value, (bool, int, float)): return value
    return str(value)[:1000]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "structured", {"message": record.getMessage()})
        return json.dumps(redact(payload), sort_keys=True, separators=(",", ":"))


def error_logger() -> logging.Logger:
    logger = logging.getLogger("jamesos.errors")
    if not logger.handlers:
        handler = logging.StreamHandler(); handler.setFormatter(JsonFormatter()); logger.addHandler(handler)
    logger.setLevel(logging.INFO); logger.propagate = False
    return logger
