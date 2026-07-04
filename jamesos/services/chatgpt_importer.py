from __future__ import annotations

import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job

IMPORT_ROOT = VAULT / "JamesOS" / "Imports" / "ChatGPT"
ARCHIVE_ROOT = VAULT / "Archive" / "ChatGPT" / "Exports"
BRAIN_ROOT = VAULT / "JamesOS" / "Brain" / "Conversations" / "ChatGPT"
INDEX_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Index"
MEMORY_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Candidate Memories"
DECISION_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Decisions"
REPORT_ROOT = VAULT / "JamesOS" / "Reports"
TIMELINE_ROOT = VAULT / "JamesOS" / "Timeline"

PROJECT_KEYWORDS = {
    "JamesOS": ["jamesos", "jade", "tasker", "obsidian", "knowledge engine", "world model", "ingest", "ollama"],
    "CGI/WGL": ["cgi", "wgl", "washington gas", "paving", "ferc", "cpmp", "wr", "work request", "oracle", "pl/sql", "sfm", "r2qa", "malcolm", "kevin", "tom"],
    "GCU Teaching": ["gcu", "student", "grading", "dq", "cst", "sym", "dsc", "announcement", "rubric"],
    "Home Lab": ["desktop", "server", "docker", "linux", "mint", "ollama", "plex", "sunshine"],
    "UnityStitches": ["etsy", "unitystitches", "unity stitches", "shop"],
    "Supreme Yard Signs": ["yard sign", "supreme yard signs", "graduation sign"],
    "Family": ["wife", "daughter", "kids", "family", "school", "camp", "birthday"],
}

DECISION_PATTERNS = [
    re.compile(r"\bwe (decided|decide|should|will|need to)\b", re.I),
    re.compile(r"\blet'?s\b", re.I),
    re.compile(r"\bdecision\b", re.I),
    re.compile(r"\bthe plan is\b", re.I),
    re.compile(r"\bi think we should\b", re.I),
]

MEMORY_PATTERNS = [
    re.compile(r"\bi (am|work|use|have|prefer|like|don'?t like|own|teach|live|want|need)\b", re.I),
    re.compile(r"\bmy (wife|daughter|job|work|laptop|desktop|phone|server|house|family)\b", re.I),
]


def _now() -> datetime:
    return datetime.now()


def _safe_filename(value: str, fallback: str = "conversation") -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value or "").strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        value = fallback
    return value[:90].strip(" ._") or fallback


def _dt_from_timestamp(value: Any) -> datetime:
    try:
        if value:
            return datetime.fromtimestamp(float(value))
    except Exception:
        pass
    return _now()


def _date_path(root: Path, dt: datetime) -> Path:
    path = root / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _archive_export(zip_path: Path) -> Path:
    dt = _now()
    target_dir = _date_path(ARCHIVE_ROOT, dt)
    target = target_dir / zip_path.name
    if zip_path.resolve() == target.resolve():
        return target
    if not target.exists():
        shutil.copy2(zip_path, target)
    return target


def _conversation_text_parts(conv: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conv.get("mapping") or {}
    rows = []
    for node_id, node in mapping.items():
        msg = (node or {}).get("message") or {}
        if not msg:
            continue
        author = (msg.get("author") or {}).get("role") or "unknown"
        create_time = msg.get("create_time") or msg.get("update_time") or conv.get("create_time")
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        text_chunks = []
        for part in parts:
            if isinstance(part, str):
                text_chunks.append(part)
            elif isinstance(part, dict):
                text_chunks.append(json.dumps(part, ensure_ascii=False)[:4000])
        text = "\n".join(t for t in text_chunks if t).strip()
        if not text:
            continue
        rows.append({
            "node_id": node_id,
            "role": author,
            "created_at": _dt_from_timestamp(create_time),
            "text": text,
        })
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _conversation_markdown(conv: dict[str, Any], rows: list[dict[str, Any]], projects: list[str]) -> str:
    title = conv.get("title") or "Untitled Conversation"
    created = _dt_from_timestamp(conv.get("create_time"))
    updated = _dt_from_timestamp(conv.get("update_time") or conv.get("create_time"))
    lines = [
        f"# {title}",
        "",
        f"Conversation ID: `{conv.get('id', '')}`",
        f"Created: {created.isoformat(timespec='seconds')}",
        f"Updated: {updated.isoformat(timespec='seconds')}",
        f"Projects: {', '.join(projects) if projects else 'Unclassified'}",
        "",
        "## Conversation",
        "",
    ]
    for row in rows:
        role = row["role"]
        ts = row["created_at"].isoformat(timespec="seconds")
        text = row["text"].strip()
        lines.extend([f"### {role} - {ts}", "", text, ""])
    return "\n".join(lines)


def _classify_projects(text: str) -> list[str]:
    lower = text.lower()
    projects = []
    for project, keywords in PROJECT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            projects.append(project)
    return projects


def _extract_candidates(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    memories = []
    decisions = []
    for row in rows:
        text = re.sub(r"\s+", " ", row["text"]).strip()
        if not text or len(text) < 25:
            continue
        if row["role"] == "user" and any(p.search(text) for p in MEMORY_PATTERNS):
            memories.append(text[:500])
        if any(p.search(text) for p in DECISION_PATTERNS):
            decisions.append(text[:700])
    return memories[:8], decisions[:8]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _write_candidate_file(root: Path, conv_id: str, title: str, items: list[str], item_label: str) -> Path | None:
    if not items:
        return None
    path = root / f"{_safe_filename(title)}-{conv_id[:8]}.md"
    lines = [f"# ChatGPT {item_label}: {title}", "", f"Conversation: `{conv_id}`", "", f"## Candidate {item_label}", ""]
    for item in items:
        lines.append(f"- {item}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _timeline_append(dt: datetime, title: str, conv_id: str, projects: list[str], memories: int, decisions: int) -> None:
    TIMELINE_ROOT.mkdir(parents=True, exist_ok=True)
    path = TIMELINE_ROOT / f"{dt.strftime('%Y-%m-%d')}.md"
    block = "\n".join([
        "",
        f"## ChatGPT Conversation - {title}",
        f"- Conversation ID: `{conv_id}`",
        f"- Projects: {', '.join(projects) if projects else 'Unclassified'}",
        f"- Candidate memories: {memories}",
        f"- Candidate decisions: {decisions}",
    ])
    with path.open("a", encoding="utf-8") as f:
        f.write(block + "\n")


def _load_conversations_from_zip(zip_path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        candidate = next((n for n in names if n.endswith("conversations.json")), None)
        if not candidate:
            raise FileNotFoundError("conversations.json not found in ChatGPT export")
        with z.open(candidate) as f:
            return json.load(f)


def import_chatgpt_export(zip_path: str | Path, limit: int | None = None) -> dict[str, Any]:
    zip_path = Path(zip_path).expanduser()
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))

    archive = _archive_export(zip_path)
    conversations = _load_conversations_from_zip(zip_path)
    if limit:
        conversations = conversations[:limit]

    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    DECISION_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    index_path = INDEX_ROOT / "conversations_index.jsonl"
    progress_path = REPORT_ROOT / "ChatGPT Import Progress.md"
    report_path = REPORT_ROOT / "ChatGPT Import Report.md"

    stats = {
        "status": "running",
        "archive": str(archive),
        "total": len(conversations),
        "imported": 0,
        "messages": 0,
        "candidate_memories": 0,
        "candidate_decisions": 0,
        "projects": Counter(),
        "started_at": _now().isoformat(timespec="seconds"),
    }

    for idx, conv in enumerate(conversations, start=1):
        conv_id = str(conv.get("id") or f"conversation-{idx}")
        title = conv.get("title") or "Untitled Conversation"
        created = _dt_from_timestamp(conv.get("create_time"))
        rows = _conversation_text_parts(conv)
        full_text = "\n".join(row["text"] for row in rows)
        projects = _classify_projects(f"{title}\n{full_text}")
        memories, decisions = _extract_candidates(rows)

        out_dir = _date_path(BRAIN_ROOT, created)
        base = f"{created.strftime('%H%M%S')}-{_safe_filename(title)}-{conv_id[:8]}"
        md_path = out_dir / f"{base}.md"
        json_path = out_dir / f"{base}.json"

        md_path.write_text(_conversation_markdown(conv, rows, projects), encoding="utf-8")
        _write_json(json_path, {
            "id": conv_id,
            "title": title,
            "created_at": created.isoformat(timespec="seconds"),
            "updated_at": _dt_from_timestamp(conv.get("update_time") or conv.get("create_time")).isoformat(timespec="seconds"),
            "projects": projects,
            "message_count": len(rows),
            "markdown_path": str(md_path),
            "candidate_memories": memories,
            "candidate_decisions": decisions,
        })

        _append_jsonl(index_path, {
            "id": conv_id,
            "title": title,
            "created_at": created.isoformat(timespec="seconds"),
            "projects": projects,
            "message_count": len(rows),
            "path": str(md_path),
            "snippet": full_text[:1000],
        })

        _write_candidate_file(MEMORY_ROOT, conv_id, title, memories, "Memories")
        _write_candidate_file(DECISION_ROOT, conv_id, title, decisions, "Decisions")
        _timeline_append(created, title, conv_id, projects, len(memories), len(decisions))

        enqueue_job("intake", {
            "title": f"ChatGPT Conversation - {title}",
            "content": full_text[:12000],
            "source": "chatgpt_export",
            "source_detail": str(md_path),
        })

        stats["imported"] += 1
        stats["messages"] += len(rows)
        stats["candidate_memories"] += len(memories)
        stats["candidate_decisions"] += len(decisions)
        stats["projects"].update(projects or ["Unclassified"])

        if idx == 1 or idx % 25 == 0 or idx == len(conversations):
            progress_path.write_text(_report_markdown(stats, final=False), encoding="utf-8")

    stats["status"] = "complete"
    stats["completed_at"] = _now().isoformat(timespec="seconds")
    report_path.write_text(_report_markdown(stats, final=True), encoding="utf-8")
    progress_path.write_text(_report_markdown(stats, final=True), encoding="utf-8")

    return {
        "status": "ok",
        "archive": str(archive),
        "report": str(report_path),
        "progress": str(progress_path),
        "index": str(index_path),
        "imported": stats["imported"],
        "messages": stats["messages"],
        "candidate_memories": stats["candidate_memories"],
        "candidate_decisions": stats["candidate_decisions"],
        "projects": dict(stats["projects"]),
    }


def _report_markdown(stats: dict[str, Any], final: bool) -> str:
    project_lines = []
    projects = stats.get("projects") or {}
    if hasattr(projects, "most_common"):
        items = projects.most_common()
    else:
        items = sorted(projects.items(), key=lambda kv: kv[1], reverse=True)
    for project, count in items[:20]:
        project_lines.append(f"- {project}: {count}")

    imported = stats.get("imported", 0)
    total = stats.get("total", 0)
    pct = round((imported / total) * 100, 1) if total else 0
    return "\n".join([
        "# ChatGPT Import Report" if final else "# ChatGPT Import Progress",
        "",
        f"Status: {stats.get('status')}",
        f"Started: {stats.get('started_at')}",
        f"Completed: {stats.get('completed_at', '')}",
        f"Archive: {stats.get('archive')}",
        "",
        "## Progress",
        "",
        f"- Conversations: {imported} / {total} ({pct}%)",
        f"- Messages: {stats.get('messages', 0)}",
        f"- Candidate memories: {stats.get('candidate_memories', 0)}",
        f"- Candidate decisions: {stats.get('candidate_decisions', 0)}",
        "",
        "## Project Buckets",
        "",
        *(project_lines or ["- None yet"]),
        "",
        "## Output",
        "",
        f"- Conversations: `{BRAIN_ROOT}`",
        f"- Candidate memories: `{MEMORY_ROOT}`",
        f"- Candidate decisions: `{DECISION_ROOT}`",
        f"- Search index: `{INDEX_ROOT / 'conversations_index.jsonl'}`",
    ]) + "\n"
