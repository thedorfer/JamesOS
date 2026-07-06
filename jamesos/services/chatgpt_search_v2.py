from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT

BRAIN_ROOT = VAULT / "JamesOS" / "Brain" / "Conversations" / "ChatGPT"
INDEX_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Index"
DB_PATH = INDEX_ROOT / "chatgpt_message_index.db"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _text_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_text_from_value(v) for v in value)))
    if isinstance(value, dict):
        for key in ("parts", "text", "value", "content", "result"):
            if key in value:
                text = _text_from_value(value.get(key))
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _role(msg: dict[str, Any]) -> str:
    author = msg.get("author")
    if isinstance(author, dict):
        return author.get("role") or author.get("name") or "unknown"
    return msg.get("role") or msg.get("sender") or "unknown"


def _dt(value: Any) -> str:
    if value is None:
        return _now()
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    try:
        return datetime.fromtimestamp(float(value)).isoformat(timespec="seconds")
    except Exception:
        return str(value)


def _rows_from_mapping(conv: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mapping = conv.get("mapping") or {}
    for node_id, node in mapping.items():
        msg = (node or {}).get("message") or {}
        if not msg:
            continue
        text = _text_from_value(msg.get("content"))
        if not text:
            continue
        rows.append({
            "external_id": node_id,
            "role": _role(msg),
            "created_at": _dt(msg.get("create_time") or msg.get("update_time") or conv.get("create_time")),
            "model": (msg.get("metadata") or {}).get("model_slug"),
            "parent": (msg.get("metadata") or {}).get("parent_id") or node.get("parent"),
            "text": text,
        })
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _items_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return [data]
    return []


def _parse_markdown_messages(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    headers = list(re.finditer(r"^###\s+(.+)$", text, flags=re.M))
    if not headers:
        return []

    rows: list[dict[str, Any]] = []
    for index, match in enumerate(headers):
        header_text = match.group(1).strip()
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[start:end].lstrip("\n").rstrip()

        role = "unknown"
        created_at = ""
        model = None

        if " - " in header_text:
            role_part, _, created_at = header_text.rpartition(" - ")
            created_at = created_at.strip()
        else:
            role_part = header_text

        role_match = re.match(r"^(user|assistant|tool|system)\s*(?:\(([^)]+)\))?$", role_part.strip(), flags=re.I)
        if role_match:
            role = role_match.group(1).lower()
            model = role_match.group(2)
        else:
            role = role_part.split()[0].strip().lower() if role_part else "unknown"

        rows.append({
            "external_id": f"{path.stem}-{len(rows)+1}",
            "role": role,
            "created_at": created_at,
            "model": model,
            "parent": None,
            "text": body,
        })
    return rows


def _conversation_metadata_from_json(path: Path) -> tuple[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.stem, ""
    conv = payload if isinstance(payload, dict) else {}
    return (
        str(conv.get("conversation_id") or conv.get("id") or path.stem),
        str(conv.get("title") or "Untitled Conversation"),
    )


def _conversation_metadata_from_markdown(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.M)
    conv_id_match = re.search(r"^Conversation ID:\s*`([^`]+)`", text, flags=re.M)
    return (
        conv_id_match.group(1) if conv_id_match else path.stem,
        title_match.group(1).strip() if title_match else "Untitled Conversation",
    )


def _fts_query(query: str) -> str:
    terms = [t for t in re.findall(r"[A-Za-z0-9_#.-]{2,}", query)]
    return " OR ".join(f"{term}*" for term in terms) if terms else ""


def connect() -> sqlite3.Connection:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT NOT NULL UNIQUE,
                conversation_id TEXT,
                title TEXT,
                role TEXT,
                created_at TEXT,
                model TEXT,
                parent TEXT,
                text TEXT,
                path TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5(
                text,
                title,
                role,
                conversation_id,
                content='messages',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO message_search(rowid, text, title, role, conversation_id)
                VALUES (new.id, new.text, new.title, new.role, new.conversation_id);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO message_search(message_search, rowid, text, title, role, conversation_id)
                VALUES('delete', old.id, old.text, old.title, old.role, old.conversation_id);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO message_search(message_search, rowid, text, title, role, conversation_id)
                VALUES('delete', old.id, old.text, old.title, old.role, old.conversation_id);
                INSERT INTO message_search(rowid, text, title, role, conversation_id)
                VALUES (new.id, new.text, new.title, new.role, new.conversation_id);
            END;
            """
        )


def index_message(message: dict[str, Any]) -> int:
    init_db()
    created_at = message.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages(
                external_id, conversation_id, title, role, created_at, model, parent, text, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                conversation_id=excluded.conversation_id,
                title=excluded.title,
                role=excluded.role,
                created_at=excluded.created_at,
                model=excluded.model,
                parent=excluded.parent,
                text=excluded.text,
                path=excluded.path
            """,
            (
                str(message.get("external_id") or ""),
                str(message.get("conversation_id") or ""),
                str(message.get("title") or ""),
                str(message.get("role") or ""),
                str(created_at or ""),
                str(message.get("model") or ""),
                str(message.get("parent") or ""),
                str(message.get("text") or ""),
                str(message.get("path") or ""),
            ),
        )
        row = conn.execute(
            "SELECT id FROM messages WHERE external_id=?",
            (str(message.get("external_id") or ""),),
        ).fetchone()
    return int(row["id"])


def search_messages(query: str, limit: int = 8) -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"status": "missing", "query": query, "results": [], "message": "ChatGPT message index has not been imported yet."}
    fts_query = _fts_query(query)
    if not fts_query:
        return {"status": "ok", "query": query, "results": [], "count": 0}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.external_id, m.conversation_id, m.title, m.role, m.created_at,
                   m.model, m.parent, m.text, m.path,
                   bm25(message_search) AS rank
            FROM message_search
            JOIN messages m ON m.id = message_search.rowid
            WHERE message_search MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    results = [dict(row) for row in rows]
    return {"status": "ok", "query": query, "results": results, "count": len(results)}


def history_context(query: str, limit: int = 6) -> str:
    result = search_messages(query, limit=limit)
    rows = result.get("results") or []
    if not rows:
        return "No matching imported ChatGPT history found."
    lines = ["# Imported ChatGPT History Matches", ""]
    for item in rows:
        lines.extend([
            f"## {item.get('title', 'Untitled Conversation')} ({item.get('role', 'unknown')})",
            f"- Date: {item.get('created_at', '')}",
            f"- Conversation ID: {item.get('conversation_id', '')}",
            f"- Path: {item.get('path', '')}",
            f"- Model: {item.get('model', 'unknown')}",
            "",
            str(item.get('text', ''))[:1200],
            "",
        ])
    return "\n".join(lines)


def _message_markdown(conv_id: str, title: str, row: dict[str, Any]) -> str:
    parts = [
        f"# ChatGPT Message",
        "",
        f"Conversation ID: `{conv_id}`",
        f"Conversation title: {title}",
        f"Role: {row.get('role', 'unknown')}",
        f"Created: {row.get('created_at', '')}",
        f"Model: {row.get('model', '')}",
        f"Parent: {row.get('parent', '')}",
        "",
        str(row.get('text', '')).rstrip(),
        "",
    ]
    return "\n".join(parts)


def _write_message_markdown(conv_id: str, title: str, row: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_message_markdown(conv_id, title, row), encoding="utf-8")


def write_message_markdown(conv_id: str, title: str, row: dict[str, Any], path: Path) -> None:
    _write_message_markdown(conv_id, title, row, path)


def rebuild_message_index() -> dict[str, Any]:
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    indexed = 0
    parsed = 0
    scanned = 0

    markdown_files = sorted(BRAIN_ROOT.rglob("*.md"))
    if markdown_files:
        for md_path in markdown_files:
            if md_path.parent.name == "messages":
                continue
            scanned += 1
            conv_id, title = _conversation_metadata_from_markdown(md_path)
            rows = _parse_markdown_messages(md_path)
            if not rows:
                continue
            parsed += len(rows)
            message_dir = md_path.parent / "messages"
            for idx, row in enumerate(rows, start=1):
                external_id = row.get("external_id") or f"{conv_id}-{idx}"
                message_path = message_dir / f"{md_path.stem}-msg-{idx:04d}.md"
                _write_message_markdown(conv_id, title, row, message_path)
                index_message({
                    "external_id": external_id,
                    "conversation_id": conv_id,
                    "title": title,
                    "role": row.get("role"),
                    "created_at": row.get("created_at"),
                    "model": row.get("model"),
                    "parent": row.get("parent"),
                    "text": row.get("text"),
                    "path": str(message_path),
                })
                indexed += 1
    else:
        for json_path in sorted(BRAIN_ROOT.rglob("*.json")):
            scanned += 1
            conv_id, title = _conversation_metadata_from_json(json_path)
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            items = _items_from_json(payload)
            conversation = items[0] if items else {}
            rows = _rows_from_mapping(conversation)
            if not rows:
                continue

            parsed += len(rows)
            message_dir = json_path.parent / "messages"
            for idx, row in enumerate(rows, start=1):
                external_id = row.get("external_id") or f"{conv_id}-{idx}"
                message_path = message_dir / f"{json_path.stem}-msg-{idx:04d}.md"
                _write_message_markdown(conv_id, title, row, message_path)
                index_message({
                    "external_id": external_id,
                    "conversation_id": conv_id,
                    "title": title,
                    "role": row.get("role"),
                    "created_at": row.get("created_at"),
                    "model": row.get("model"),
                    "parent": row.get("parent"),
                    "text": row.get("text"),
                    "path": str(message_path),
                })
                indexed += 1

    return {
        "status": "ok",
        "scanned": scanned,
        "parsed": parsed,
        "parsed_messages": parsed,
        "indexed": indexed,
        "db_path": str(DB_PATH),
    }
