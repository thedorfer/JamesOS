from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from jamesos.config import VAULT

DATA_DIR = VAULT / "JamesOS" / "Brain" / "Knowledge"
DB_PATH = DATA_DIR / "knowledge.db"
EXPORT_DIR = VAULT / "JamesOS" / "Reports" / "Knowledge"
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect() -> Iterable[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL,
                display_name TEXT,
                path TEXT,
                last_imported_at TEXT,
                metadata_json TEXT DEFAULT '{}',
                UNIQUE(source_type, source_key)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                external_id TEXT NOT NULL,
                thread_id TEXT,
                doc_type TEXT NOT NULL,
                title TEXT,
                body TEXT,
                snippet TEXT,
                author TEXT,
                author_email TEXT,
                created_at TEXT,
                updated_at TEXT,
                imported_at TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                UNIQUE(doc_type, external_id),
                FOREIGN KEY(source_id) REFERENCES sources(id)
            );

            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                primary_email TEXT,
                domain TEXT,
                importance REAL DEFAULT 0,
                confidence TEXT DEFAULT 'extracted',
                first_seen TEXT,
                last_seen TEXT,
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS person_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                email TEXT NOT NULL UNIQUE,
                seen_count INTEGER DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                FOREIGN KEY(person_id) REFERENCES people(id)
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT DEFAULT 'unknown',
                importance REAL DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                domain TEXT,
                importance REAL DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                importance REAL DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                entity_type TEXT,
                entity_name TEXT,
                importance REAL DEFAULT 0,
                source_document_id INTEGER,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY(source_document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                score REAL DEFAULT 0,
                mode TEXT DEFAULT 'personal',
                created_at TEXT NOT NULL,
                expires_at TEXT,
                source_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_type TEXT NOT NULL,
                from_name TEXT NOT NULL,
                to_type TEXT NOT NULL,
                to_name TEXT NOT NULL,
                relationship TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 1,
                first_seen TEXT,
                last_seen TEXT,
                metadata_json TEXT DEFAULT '{}',
                UNIQUE(from_type, from_name, to_type, to_name, relationship)
            );

            CREATE TABLE IF NOT EXISTS document_people (
                document_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                role TEXT DEFAULT 'mentioned',
                PRIMARY KEY(document_id, person_id, role),
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(person_id) REFERENCES people(id)
            );

            CREATE TABLE IF NOT EXISTS document_projects (
                document_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                PRIMARY KEY(document_id, project_id),
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS document_topics (
                document_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                PRIMARY KEY(document_id, topic_id),
                FOREIGN KEY(document_id) REFERENCES documents(id),
                FOREIGN KEY(topic_id) REFERENCES topics(id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(
                title,
                body,
                snippet,
                content='documents',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO document_search(rowid, title, body, snippet)
                VALUES (new.id, new.title, new.body, new.snippet);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO document_search(document_search, rowid, title, body, snippet)
                VALUES('delete', old.id, old.title, old.body, old.snippet);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO document_search(document_search, rowid, title, body, snippet)
                VALUES('delete', old.id, old.title, old.body, old.snippet);
                INSERT INTO document_search(rowid, title, body, snippet)
                VALUES (new.id, new.title, new.body, new.snippet);
            END;
            """
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("initialized_at", utc_now()),
        )

    return knowledge_status()


def json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def upsert_source(source_type: str, source_key: str, display_name: str | None = None, path: str | None = None, metadata: dict | None = None) -> int:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sources(source_type, source_key, display_name, path, last_imported_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_key) DO UPDATE SET
                display_name=excluded.display_name,
                path=excluded.path,
                last_imported_at=excluded.last_imported_at,
                metadata_json=excluded.metadata_json
            """,
            (source_type, source_key, display_name, path, utc_now(), json_dumps(metadata)),
        )
        row = conn.execute(
            "SELECT id FROM sources WHERE source_type=? AND source_key=?",
            (source_type, source_key),
        ).fetchone()
        return int(row["id"])


def upsert_document(record: dict[str, Any]) -> int:
    init_db()
    source_id = record.get("source_id")
    imported_at = record.get("imported_at") or utc_now()
    metadata = record.get("metadata") or {}

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO documents(
                source_id, external_id, thread_id, doc_type, title, body, snippet,
                author, author_email, created_at, updated_at, imported_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_type, external_id) DO UPDATE SET
                source_id=excluded.source_id,
                thread_id=excluded.thread_id,
                title=excluded.title,
                body=excluded.body,
                snippet=excluded.snippet,
                author=excluded.author,
                author_email=excluded.author_email,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                imported_at=excluded.imported_at,
                metadata_json=excluded.metadata_json
            """,
            (
                source_id,
                record["external_id"],
                record.get("thread_id"),
                record.get("doc_type", "document"),
                record.get("title"),
                record.get("body"),
                record.get("snippet"),
                record.get("author"),
                record.get("author_email"),
                record.get("created_at"),
                record.get("updated_at"),
                imported_at,
                json_dumps(metadata),
            ),
        )
        row = conn.execute(
            "SELECT id FROM documents WHERE doc_type=? AND external_id=?",
            (record.get("doc_type", "document"), record["external_id"]),
        ).fetchone()
        return int(row["id"])


def upsert_named(table: str, name: str, **fields: Any) -> int:
    if table not in {"people", "projects", "companies", "topics"}:
        raise ValueError(f"Unsupported table: {table}")
    init_db()
    now = fields.get("last_seen") or utc_now()
    first_seen = fields.get("first_seen") or now
    metadata = json_dumps(fields.get("metadata"))

    with connect() as conn:
        if table == "people":
            conn.execute(
                """
                INSERT INTO people(name, primary_email, domain, importance, confidence, first_seen, last_seen, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    primary_email=COALESCE(excluded.primary_email, people.primary_email),
                    domain=COALESCE(excluded.domain, people.domain),
                    importance=MAX(people.importance, excluded.importance),
                    last_seen=excluded.last_seen
                """,
                (name, fields.get("primary_email"), fields.get("domain"), fields.get("importance", 0), fields.get("confidence", "extracted"), first_seen, now, metadata),
            )
        else:
            conn.execute(
                f"""
                INSERT INTO {table}(name, importance, first_seen, last_seen, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    importance=MAX({table}.importance, excluded.importance),
                    last_seen=excluded.last_seen
                """,
                (name, fields.get("importance", 0), first_seen, now, metadata),
            )
        row = conn.execute(f"SELECT id FROM {table} WHERE name=?", (name,)).fetchone()
        return int(row["id"])


def add_signal(kind: str, title: str, body: str = "", score: float = 0, mode: str = "personal", source: dict | None = None) -> int:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO signals(kind, title, body, score, mode, created_at, source_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, title, body, score, mode, utc_now(), json_dumps(source)),
        )
        return int(cur.lastrowid)


def search_documents(query: str, limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.doc_type, d.title, d.snippet, d.author, d.author_email, d.created_at,
                   bm25(document_search) AS rank
            FROM document_search
            JOIN documents d ON d.id = document_search.rowid
            WHERE document_search MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def top_rows(table: str, limit: int = 10) -> list[dict[str, Any]]:
    if table not in {"people", "projects", "companies", "topics", "signals", "documents"}:
        raise ValueError(f"Unsupported table: {table}")
    order = "score DESC" if table == "signals" else "importance DESC, last_seen DESC"
    if table == "documents":
        order = "created_at DESC"
    with connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order} LIMIT ?", (limit,)).fetchall()]


def knowledge_status() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        return {"status": "missing", "db_path": str(DB_PATH)}
    with connect() as conn:
        counts = {}
        for table in ["sources", "documents", "people", "projects", "companies", "topics", "timeline", "signals", "relationships"]:
            counts[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "schema_version": version["value"] if version else None,
        "counts": counts,
    }


def export_obsidian_reports() -> str:
    init_db()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    people = top_rows("people", 25)
    projects = top_rows("projects", 25)
    signals = top_rows("signals", 25)

    report = [
        "# JamesOS Knowledge Engine",
        "",
        f"Generated: {utc_now()}",
        "",
        "## Status",
        "",
        "```json",
        json.dumps(knowledge_status(), indent=2),
        "```",
        "",
        "## Top Signals",
    ]
    for row in signals:
        report.append(f"- **{row.get('title')}** ({row.get('mode')}, score {row.get('score')}): {row.get('body') or ''}")

    report.extend(["", "## Top People"])
    for row in people:
        report.append(f"- **{row.get('name')}** — {row.get('primary_email') or ''} importance {row.get('importance')}")

    report.extend(["", "## Top Projects"])
    for row in projects:
        report.append(f"- **{row.get('name')}** — status {row.get('status')} importance {row.get('importance')}")

    path = EXPORT_DIR / "Knowledge Engine.md"
    path.write_text("\n".join(report), encoding="utf-8")
    return f"Exported {path}"
