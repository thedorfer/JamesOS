from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services.knowledge_db import add_signal, init_db, upsert_document, upsert_source

PHONE_DIR = VAULT / "JamesOS" / "Brain" / "Phone"
RAW_DIR = PHONE_DIR / "Raw"
REPORT_DIR = VAULT / "JamesOS" / "Reports" / "Phone"

VALID_TYPES = {"call", "sms", "rcs", "messenger", "line", "notification"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe(value: Any) -> str:
    return str(value or "").strip()


def _normalize_type(value: str) -> str:
    item_type = _safe(value).lower().replace(" ", "_")
    aliases = {
        "phone": "call",
        "phone_call": "call",
        "text": "sms",
        "fb": "messenger",
        "facebook": "messenger",
        "facebook_messenger": "messenger",
        "line_messenger": "line",
    }
    item_type = aliases.get(item_type, item_type)
    if item_type not in VALID_TYPES:
        item_type = "notification"
    return item_type


def _external_id(item: dict[str, Any]) -> str:
    device = _safe(item.get("device") or "android")
    source_type = _normalize_type(item.get("type") or item.get("source_type") or "notification")
    timestamp = _safe(item.get("timestamp") or item.get("date") or item.get("time") or utc_now())
    person = _safe(item.get("person") or item.get("name") or item.get("number") or item.get("sender") or "unknown")
    text = _safe(item.get("text") or item.get("body") or item.get("title") or item.get("summary"))
    return f"phone:{device}:{source_type}:{timestamp}:{person}:{hash(text)}"


def _title(item: dict[str, Any], source_type: str) -> str:
    person = _safe(item.get("person") or item.get("name") or item.get("number") or item.get("sender") or "Unknown")
    app = _safe(item.get("app") or item.get("package") or source_type.title())
    direction = _safe(item.get("direction") or item.get("call_type") or "")
    if source_type == "call":
        return f"Call {direction} - {person}".replace("  ", " ").strip()
    if source_type in {"sms", "rcs"}:
        return f"{source_type.upper()} - {person}"
    return f"{app} - {person}"


def _body(item: dict[str, Any], source_type: str) -> str:
    lines = [
        f"Type: {source_type}",
        f"App: {_safe(item.get('app') or item.get('package'))}",
        f"Person: {_safe(item.get('person') or item.get('name') or item.get('sender'))}",
        f"Number: {_safe(item.get('number') or item.get('phone'))}",
        f"Direction: {_safe(item.get('direction') or item.get('call_type'))}",
        f"Timestamp: {_safe(item.get('timestamp') or item.get('date') or item.get('time'))}",
        f"Duration: {_safe(item.get('duration'))}",
        "",
        _safe(item.get("text") or item.get("body") or item.get("title") or item.get("summary")),
    ]
    return "\n".join(line for line in lines if line is not None)


def ingest_phone_event(item: dict[str, Any]) -> dict[str, Any]:
    init_db()
    PHONE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    source_type = _normalize_type(item.get("type") or item.get("source_type") or "notification")
    device = _safe(item.get("device") or "android")
    source_id = upsert_source("phone", f"{device}:{source_type}", f"Phone {source_type}")

    external_id = _external_id(item)
    title = _title(item, source_type)
    body = _body(item, source_type)
    timestamp = _safe(item.get("timestamp") or item.get("date") or item.get("time") or utc_now())

    doc_id = upsert_document({
        "source_id": source_id,
        "external_id": external_id,
        "doc_type": f"phone_{source_type}",
        "title": title,
        "body": body,
        "snippet": body[:300],
        "author": _safe(item.get("person") or item.get("name") or item.get("sender")),
        "author_email": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "metadata": item,
    })

    day = datetime.now().strftime("%Y-%m-%d")
    raw_path = RAW_DIR / f"{day}.jsonl"
    with raw_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ingested_at": utc_now(), "document_id": doc_id, **item}, ensure_ascii=False) + "\n")

    text = _safe(item.get("text") or item.get("body") or item.get("summary"))
    if source_type in {"sms", "rcs", "messenger", "line"} and text:
        add_signal(
            "phone_message",
            title,
            text[:500],
            score=4.0,
            mode="personal",
            source={"document_id": doc_id, "source_type": source_type},
        )

    return {"status": "ok", "document_id": doc_id, "type": source_type, "title": title}


def ingest_phone_events(items: list[dict[str, Any]]) -> dict[str, Any]:
    results = [ingest_phone_event(item) for item in items]
    return {"status": "ok", "count": len(results), "results": results}


def phone_daily_summary() -> str:
    PHONE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    raw_path = RAW_DIR / f"{today}.jsonl"

    counts: dict[str, int] = {}
    people: dict[str, int] = {}
    samples: list[str] = []

    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            source_type = _normalize_type(item.get("type") or item.get("source_type") or "notification")
            counts[source_type] = counts.get(source_type, 0) + 1
            person = _safe(item.get("person") or item.get("name") or item.get("sender") or item.get("number") or "Unknown")
            people[person] = people.get(person, 0) + 1
            if len(samples) < 12:
                text = _safe(item.get("text") or item.get("body") or item.get("summary") or item.get("title"))
                samples.append(f"- **{source_type}** {person}: {text[:140]}")

    report = [
        "# Phone Daily Summary",
        "",
        f"Date: {today}",
        "",
        "## Counts",
        "",
    ]
    if counts:
        report.extend([f"- {k}: {v}" for k, v in sorted(counts.items())])
    else:
        report.append("- No phone events ingested today yet.")

    report.extend(["", "## Top People", ""])
    for person, count in sorted(people.items(), key=lambda kv: kv[1], reverse=True)[:10]:
        report.append(f"- {person}: {count}")

    report.extend(["", "## Samples", ""])
    report.extend(samples or ["- None yet."])

    out = REPORT_DIR / "Phone Daily Summary.md"
    out.write_text("\n".join(report), encoding="utf-8")
    return str(out)
