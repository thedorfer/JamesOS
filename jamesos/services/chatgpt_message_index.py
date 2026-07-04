from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from jamesos.config import VAULT

DB_PATH = VAULT / "JamesOS" / "Database" / "chatgpt_messages.sqlite3"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            updated_at TEXT,
            projects TEXT,
            markdown_path TEXT,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            node_id TEXT,
            role TEXT,
            created_at TEXT,
            model TEXT,
            text TEXT,
            title TEXT,
            projects TEXT,
            markdown_path TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            title,
            role,
            text,
            projects,
            content='messages',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, title, role, text, projects)
            VALUES (new.rowid, new.title, new.role, new.text, new.projects);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, title, role, text, projects)
            VALUES('delete', old.rowid, old.title, old.role, old.text, old.projects);
        END;

        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, title, role, text, projects)
            VALUES('delete', old.rowid, old.title, old.role, old.text, old.projects);
            INSERT INTO messages_fts(rowid, title, role, text, projects)
            VALUES (new.rowid, new.title, new.role, new.text, new.projects);
        END;
        """
    )
    conn.commit()
    if own:
        conn.close()


def reset_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    init_db()


def upsert_conversation(conn: sqlite3.Connection, item: dict[str, Any]) -> None:
    init_db(conn)
    conn.execute(
        """
        INSERT INTO conversations(conversation_id, title, created_at, updated_at, projects, markdown_path, message_count)
        VALUES(:conversation_id, :title, :created_at, :updated_at, :projects, :markdown_path, :message_count)
        ON CONFLICT(conversation_id) DO UPDATE SET
            title=excluded.title,
            created_at=excluded.created_at,
            updated_at=excluded.updated_at,
            projects=excluded.projects,
            markdown_path=excluded.markdown_path,
            message_count=excluded.message_count
        """,
        item,
    )


def index_messages(conn: sqlite3.Connection, conversation: dict[str, Any], rows: Iterable[dict[str, Any]], markdown_path: str, projects: list[str]) -> None:
    init_db(conn)
    conv_id = str(conversation.get("conversation_id") or conversation.get("id") or "")
    title = conversation.get("title") or "Untitled Conversation"
    project_text = ", ".join(projects or ["Unclassified"])

    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    for i, row in enumerate(rows):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        message_id = f"{conv_id}:{row.get('node_id') or i}"
        conn.execute(
            """
            INSERT OR REPLACE INTO messages(
                message_id, conversation_id, node_id, role, created_at, model, text, title, projects, markdown_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conv_id,
                str(row.get("node_id") or i),
                str(row.get("role") or "unknown"),
                row.get("created_at").isoformat(timespec="seconds") if hasattr(row.get("created_at"), "isoformat") else str(row.get("created_at") or ""),
                row.get("model") or "",
                text,
                title,
                project_text,
                markdown_path,
            ),
        )


def _terms(query: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_#.-]{2,}", query) if t.lower() not in {"what", "know", "about", "from", "your", "chatgpt", "history", "the", "and", "for"}][:12]


def _fts_query(query: str) -> str:
    terms = _terms(query)
    if not terms:
        return query.strip()
    return " OR ".join(f'"{t}"' for t in terms)


def _snippet(text: str, terms: list[str], size: int = 900) -> str:
    if not text:
        return ""
    lower = text.lower()
    hits = [lower.find(t) for t in terms if lower.find(t) >= 0]
    if not hits:
        return text[:size]
    start = max(min(hits) - 220, 0)
    end = min(start + size, len(text))
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def search_messages(query: str, limit: int = 12) -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"status": "missing", "query": query, "results": [], "message": "ChatGPT message index has not been built yet."}
    terms = _terms(query)
    fts = _fts_query(query)
    with connect() as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                m.conversation_id,
                m.title,
                m.created_at,
                m.role,
                m.text,
                m.projects,
                m.markdown_path,
                m.model,
                bm25(messages_fts) AS rank
            FROM messages_fts
            JOIN messages m ON m.rowid = messages_fts.rowid
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts, limit * 4),
        ).fetchall()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        conv_id = row["conversation_id"]
        text = row["text"] or ""
        score = 0
        title_lower = (row["title"] or "").lower()
        text_lower = text.lower()
        projects_lower = (row["projects"] or "").lower()
        for term in terms:
            if term in title_lower:
                score += 8
            if term in projects_lower:
                score += 4
            score += min(text_lower.count(term), 8)
        score += max(0, 8 - len(grouped.get(conv_id, {}).get("matches", [])))

        item = grouped.setdefault(conv_id, {
            "id": conv_id,
            "title": row["title"],
            "created_at": row["created_at"],
            "projects": [p.strip() for p in (row["projects"] or "Unclassified").split(",") if p.strip()],
            "path": row["markdown_path"],
            "score": 0,
            "matches": [],
            "snippet": "",
        })
        item["score"] += score
        if len(item["matches"]) < 4:
            item["matches"].append({
                "role": row["role"],
                "created_at": row["created_at"],
                "model": row["model"],
                "snippet": _snippet(text, terms),
            })

    results = list(grouped.values())
    for item in results:
        item["snippet"] = "\n\n".join(f"{m['role']}: {m['snippet']}" for m in item["matches"])
        item["message_count"] = len(item["matches"])
    results.sort(key=lambda x: (x.get("score", 0), x.get("created_at", "")), reverse=True)
    return {"status": "ok", "query": query, "results": results[:limit], "count": len(results), "source": "sqlite_fts"}


def stats() -> dict[str, Any]:
    if not DB_PATH.exists():
        return {"status": "missing", "db": str(DB_PATH), "conversations": 0, "messages": 0}
    with connect() as conn:
        init_db(conn)
        conversations = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    return {"status": "ok", "db": str(DB_PATH), "conversations": conversations, "messages": messages}
