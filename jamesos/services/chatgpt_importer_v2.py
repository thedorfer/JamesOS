from __future__ import annotations

import json
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job

ARCHIVE_ROOT = VAULT / "Archive" / "ChatGPT" / "Exports"
BRAIN_ROOT = VAULT / "JamesOS" / "Brain" / "Conversations" / "ChatGPT"
INDEX_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Index"
MEMORY_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Candidate Memories"
DECISION_ROOT = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Decisions"
REPORT_ROOT = VAULT / "JamesOS" / "Reports"
TIMELINE_ROOT = VAULT / "JamesOS" / "Timeline"

PROJECT_KEYWORDS = {
    "JamesOS": ["jamesos", "jade", "tasker", "obsidian", "knowledge engine", "world model", "ingest", "ollama"],
    "CGI/WGL": ["cgi", "wgl", "washington gas", "paving", "ferc", "cpmp", "work request", "oracle", "pl/sql", "sfm", "r2qa", "malcolm", "kevin", "tom"],
    "GCU Teaching": ["gcu", "student", "grading", "dq", "cst", "sym", "dsc", "announcement", "rubric"],
    "Home Lab": ["desktop", "server", "docker", "linux", "mint", "ollama", "plex", "sunshine"],
    "Family": ["wife", "daughter", "kids", "family", "school", "camp", "birthday"],
    "UnityStitches": ["etsy", "unitystitches", "unity stitches", "shop"],
    "Supreme Yard Signs": ["yard sign", "supreme yard signs", "graduation sign"],
}

MEMORY_PATTERNS = [
    re.compile(r"\bi (am|work|use|have|prefer|like|own|teach|live|want|need)\b", re.I),
    re.compile(r"\bmy (wife|daughter|job|work|laptop|desktop|phone|server|house|family)\b", re.I),
]

DECISION_PATTERNS = [
    re.compile(r"\bwe (decided|decide|should|will|need to)\b", re.I),
    re.compile(r"\blet'?s\b", re.I),
    re.compile(r"\bdecision\b", re.I),
    re.compile(r"\bthe plan is\b", re.I),
    re.compile(r"\bi think we should\b", re.I),
]


def _now() -> datetime:
    return datetime.now()


def _safe_filename(value: str, fallback: str = "conversation") -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return (value[:90].strip(" ._") or fallback)


def _dt(value: Any) -> datetime:
    try:
        if value:
            return datetime.fromtimestamp(float(value))
    except Exception:
        pass
    return _now()


def _date_dir(root: Path, dt: datetime) -> Path:
    path = root / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _archive_zip(zip_path: Path) -> Path:
    target = _date_dir(ARCHIVE_ROOT, _now()) / zip_path.name
    if not target.exists() and zip_path.resolve() != target.resolve():
        shutil.copy2(zip_path, target)
    return target


def _text_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (_text_from_value(v) for v in value))).strip()
    if isinstance(value, dict):
        for key in ("parts", "text", "value", "content", "result"):
            if key in value:
                text = _text_from_value(value.get(key))
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False)[:4000]
    return str(value).strip()


def _role(msg: dict[str, Any]) -> str:
    author = msg.get("author")
    if isinstance(author, dict):
        return author.get("role") or author.get("name") or "unknown"
    return msg.get("role") or msg.get("sender") or "unknown"


def _rows_from_mapping(conv: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    mapping = conv.get("mapping") or {}
    for node_id, node in mapping.items():
        msg = (node or {}).get("message") or {}
        if not msg:
            continue
        text = _text_from_value(msg.get("content"))
        if not text:
            continue
        rows.append({
            "node_id": node_id,
            "role": _role(msg),
            "created_at": _dt(msg.get("create_time") or msg.get("update_time") or conv.get("create_time")),
            "model": (msg.get("metadata") or {}).get("model_slug"),
            "parent": (msg.get("metadata") or {}).get("parent_id") or node.get("parent"),
            "text": text,
        })
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _projects(text: str) -> list[str]:
    lower = text.lower()
    return [name for name, words in PROJECT_KEYWORDS.items() if any(w in lower for w in words)]


def _candidates(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    memories: list[str] = []
    decisions: list[str] = []
    for row in rows:
        text = re.sub(r"\s+", " ", row["text"]).strip()
        if len(text) < 25:
            continue
        if row["role"] == "user" and any(p.search(text) for p in MEMORY_PATTERNS):
            memories.append(text[:500])
        if any(p.search(text) for p in DECISION_PATTERNS):
            decisions.append(text[:700])
    return memories[:10], decisions[:10]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _md(conv: dict[str, Any], rows: list[dict[str, Any]], projects: list[str], created: datetime) -> str:
    title = conv.get("title") or "Untitled Conversation"
    conv_id = conv.get("conversation_id") or conv.get("id") or ""
    lines = [
        f"# {title}", "",
        f"Conversation ID: `{conv_id}`",
        f"Created: {created.isoformat(timespec='seconds')}",
        f"Projects: {', '.join(projects) if projects else 'Unclassified'}",
        "", "## Transcript", "",
    ]
    for row in rows:
        model = f" ({row['model']})" if row.get("model") else ""
        lines += [f"### {row['role']}{model} - {row['created_at'].isoformat(timespec='seconds')}", "", row["text"].strip(), ""]
    return "\n".join(lines)


def _write_candidates(root: Path, conv_id: str, title: str, items: list[str], label: str) -> None:
    if not items:
        return
    path = root / f"{_safe_filename(title)}-{conv_id[:8]}.md"
    text = [f"# ChatGPT Candidate {label}: {title}", "", f"Conversation: `{conv_id}`", ""]
    text += [f"- {item}" for item in items]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def _timeline(created: datetime, title: str, conv_id: str, projects: list[str], memories: int, decisions: int) -> None:
    TIMELINE_ROOT.mkdir(parents=True, exist_ok=True)
    path = TIMELINE_ROOT / f"{created.strftime('%Y-%m-%d')}.md"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join([
            "",
            f"## ChatGPT Conversation - {title}",
            f"- Conversation ID: `{conv_id}`",
            f"- Projects: {', '.join(projects) if projects else 'Unclassified'}",
            f"- Candidate memories: {memories}",
            f"- Candidate decisions: {decisions}",
            "",
        ]))


def _items_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return [data]
    return []


def _load_conversations(zip_path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        split = sorted(n for n in names if re.search(r"conversations-\d+\.json$", n))
        if split:
            out: list[dict[str, Any]] = []
            for name in split:
                with z.open(name) as f:
                    out.extend(_items_from_json(json.load(f)))
            return out
        one = next((n for n in names if n.endswith("conversations.json")), None)
        if not one:
            raise FileNotFoundError("No ChatGPT conversation JSON files found")
        with z.open(one) as f:
            return _items_from_json(json.load(f))


def _report(stats: dict[str, Any], final: bool) -> str:
    projects = stats["projects"].most_common() if hasattr(stats["projects"], "most_common") else stats["projects"].items()
    project_lines = [f"- {name}: {count}" for name, count in projects[:20]]
    pct = round((stats["imported"] / stats["total"]) * 100, 1) if stats["total"] else 0
    return "\n".join([
        "# ChatGPT Import Report" if final else "# ChatGPT Import Progress",
        "",
        f"Status: {stats['status']}",
        f"Started: {stats['started_at']}",
        f"Completed: {stats.get('completed_at', '')}",
        f"Archive: {stats['archive']}",
        "",
        "## Progress", "",
        f"- Conversations: {stats['imported']} / {stats['total']} ({pct}%)",
        f"- Messages: {stats['messages']}",
        f"- Empty conversations: {stats['empty']}",
        f"- Candidate memories: {stats['candidate_memories']}",
        f"- Candidate decisions: {stats['candidate_decisions']}",
        "", "## Project Buckets", "",
        *(project_lines or ["- None"]),
        "", "## Output", "",
        f"- Conversations: `{BRAIN_ROOT}`",
        f"- Candidate memories: `{MEMORY_ROOT}`",
        f"- Candidate decisions: `{DECISION_ROOT}`",
        f"- Search index: `{INDEX_ROOT / 'conversations_index.jsonl'}`",
    ]) + "\n"


def import_chatgpt_export(zip_path: str | Path, limit: int | None = None) -> dict[str, Any]:
    zip_path = Path(zip_path).expanduser()
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))

    archive = _archive_zip(zip_path)
    conversations = _load_conversations(zip_path)
    if limit:
        conversations = conversations[:limit]

    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    DECISION_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    index_path = INDEX_ROOT / "conversations_index.jsonl"
    progress_path = REPORT_ROOT / "ChatGPT Import Progress.md"
    report_path = REPORT_ROOT / "ChatGPT Import Report.md"

    stats = {"status": "running", "archive": str(archive), "total": len(conversations), "imported": 0, "messages": 0, "empty": 0, "candidate_memories": 0, "candidate_decisions": 0, "projects": Counter(), "started_at": _now().isoformat(timespec="seconds")}

    for idx, conv in enumerate(conversations, start=1):
        conv_id = str(conv.get("conversation_id") or conv.get("id") or f"conversation-{idx}")
        title = conv.get("title") or "Untitled Conversation"
        rows = _rows_from_mapping(conv)
        created = rows[0]["created_at"] if rows else _dt(conv.get("create_time"))
        if not rows:
            stats["empty"] += 1
        full_text = "\n".join(r["text"] for r in rows)
        projects = _projects(f"{title}\n{full_text}")
        memories, decisions = _candidates(rows)

        out_dir = _date_dir(BRAIN_ROOT, created)
        base = f"{created.strftime('%H%M%S')}-{_safe_filename(title)}-{conv_id[:8]}"
        md_path = out_dir / f"{base}.md"
        json_path = out_dir / f"{base}.json"
        md_path.write_text(_md(conv, rows, projects, created), encoding="utf-8")
        _write_json(json_path, {"id": conv_id, "title": title, "created_at": created.isoformat(timespec="seconds"), "projects": projects, "message_count": len(rows), "markdown_path": str(md_path), "candidate_memories": memories, "candidate_decisions": decisions})
        _append_jsonl(index_path, {"id": conv_id, "title": title, "created_at": created.isoformat(timespec="seconds"), "projects": projects, "message_count": len(rows), "path": str(md_path), "snippet": full_text[:1000]})
        _write_candidates(MEMORY_ROOT, conv_id, title, memories, "Memories")
        _write_candidates(DECISION_ROOT, conv_id, title, decisions, "Decisions")
        _timeline(created, title, conv_id, projects, len(memories), len(decisions))
        if full_text.strip():
            enqueue_job("intake", {"title": f"ChatGPT Conversation - {title}", "content": full_text[:12000], "source": "chatgpt_export", "source_detail": str(md_path)})

        stats["imported"] += 1
        stats["messages"] += len(rows)
        stats["candidate_memories"] += len(memories)
        stats["candidate_decisions"] += len(decisions)
        stats["projects"].update(projects or ["Unclassified"])
        if idx == 1 or idx % 25 == 0 or idx == len(conversations):
            progress_path.write_text(_report(stats, final=False), encoding="utf-8")

    stats["status"] = "complete"
    stats["completed_at"] = _now().isoformat(timespec="seconds")
    report_path.write_text(_report(stats, final=True), encoding="utf-8")
    progress_path.write_text(_report(stats, final=True), encoding="utf-8")
    return {"status": "ok", "archive": str(archive), "report": str(report_path), "progress": str(progress_path), "index": str(index_path), "imported": stats["imported"], "messages": stats["messages"], "empty_conversations": stats["empty"], "candidate_memories": stats["candidate_memories"], "candidate_decisions": stats["candidate_decisions"], "projects": dict(stats["projects"])}
