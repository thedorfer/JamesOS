from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job
from jamesos.services.search_service import search_notes_index
from jamesos.services.status_report import generate_status_report
from jamesos.services.briefing import generate_daily_briefing
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.rich_context import build_rich_context
from jamesos.services.agent import ask_agent, handle_jade_message
from jamesos.services.memory_service import remember, search_memory
from jamesos.services.typed_index import build_typed_indexes, search_typed_indexes
from jamesos.services.tool_router import route_tool
from jamesos.services.attachment_ingest import ingest_attachments
from jamesos.services.file_intelligence import build_file_knowledge

API_KEY_FILE = VAULT / "JamesOS" / "Secrets" / "api_key.txt"
CHAT_HISTORY_FILE = VAULT / "JamesOS" / "Memory" / "chat_history.json"

app = FastAPI(title="JamesOS API")


class IntakeRequest(BaseModel):
    title: str
    content: str
    source: str = "api"
    source_detail: str = ""


class AskRequest(BaseModel):
    question: str
    use_ai: bool = True


class QuickNoteRequest(BaseModel):
    text: str
    title: str = "Quick Note"


class ShareLinkRequest(BaseModel):
    url: str
    title: str = "Shared Link"
    note: str = ""


class MemoryRequest(BaseModel):
    text: str
    source: str = "api"
    importance: str = "normal"


class ToolRequest(BaseModel):
    question: str




def _search_query_from_question(question: str) -> str:
    q = question.strip()

    prefixes = [
        "what do you know about ",
        "tell me about ",
        "summarize ",
        "what is ",
        "who is ",
        "show me ",
        "find ",
    ]

    lower = q.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    q = q.rstrip(" ?.")
    return q or question


def _read_search_context(query: str, limit: int = 8) -> str:
    from jamesos.services.search_service import search_notes_index

    result = search_notes_index(query)
    lines = ["# Keyword Search Context", "", result, ""]

    # Pull source text from matching wikilinks when possible.
    import re
    links = re.findall(r"\[\[([^\]]+)\]\]", result)

    added = 0
    for link in links:
        if added >= limit:
            break

        target = link.split("|")[0]
        path = VAULT / f"{target}.md"

        if path.exists():
            lines.extend([
                "",
                f"## Source: [[{target}]]",
                "",
                path.read_text(encoding="utf-8", errors="ignore")[:1500],
            ])
            added += 1

    return "\n".join(lines)


def _expected_key() -> str:
    if not API_KEY_FILE.exists():
        raise HTTPException(status_code=500, detail="API key is not configured")
    return API_KEY_FILE.read_text(encoding="utf-8").strip()


def require_key(x_jamesos_key: str | None = Header(default=None)) -> None:
    if x_jamesos_key != _expected_key():
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    return {"status": "ok", "service": "JamesOS"}


@app.post("/intake")
def intake(req: IntakeRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    result = enqueue_job("intake", req.model_dump())
    return {"result": result}


@app.post("/quick-note")
def quick_note(req: QuickNoteRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    result = enqueue_job("intake", {
        "title": req.title,
        "content": req.text,
        "source": "mobile_quick_note",
        "source_detail": "flutter_app",
    })
    return {"result": result}


@app.post("/share-link")
def share_link(req: ShareLinkRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    content = f"URL: {req.url}\n\nNote:\n{req.note}"
    result = enqueue_job("intake", {
        "title": req.title,
        "content": content,
        "source": "mobile_share_link",
        "source_detail": req.url,
    })
    return {"result": result}


@app.get("/search")
def search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": search_notes_index(q)}


@app.post("/ask")
def ask(req: AskRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)

    from datetime import datetime

    result = handle_jade_message(req.question, use_ai=req.use_ai)

    history = _load_chat_history()
    history.append({
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": req.question,
        "answer": result.get("answer", ""),
        "action": result.get("action", ""),
    })
    _save_chat_history(history)

    return result


@app.get("/ask")
def ask_get(q: str, use_ai: bool = True, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return handle_jade_message(q, use_ai=use_ai)


@app.get("/daily-briefing")
def daily_briefing(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_daily_briefing()}


@app.get("/status-report")
def status_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_status_report()}


@app.get("/mobile/home")
def mobile_home(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)

    reports = VAULT / "JamesOS" / "Reports"
    home = VAULT / "Home.md"

    def read_report(name: str) -> str:
        path = reports / f"{name}.md"
        return path.read_text(encoding="utf-8", errors="ignore")[:4000] if path.exists() else ""

    return {
        "status": "ok",
        "home": home.read_text(encoding="utf-8", errors="ignore")[:4000] if home.exists() else "",
        "daily_briefing": read_report("Daily Briefing"),
        "proactive_assistant": read_report("Proactive Assistant"),
        "work_intelligence": read_report("Work Intelligence"),
        "people": read_report("People"),
    }


@app.post("/memory")
def memory_add(req: MemoryRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return remember(req.text, req.source, req.importance)


@app.get("/memory/search")
def memory_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"results": search_memory(q)}


@app.post("/indexes/build")
def indexes_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_typed_indexes()}


@app.get("/indexes/search")
def indexes_search(q: str, categories: str = "", x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    cats = [c.strip() for c in categories.split(",") if c.strip()] or None
    return search_typed_indexes(q, cats)


@app.post("/tools/route")
def tools_route(req: ToolRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return route_tool(req.question)


@app.get("/app", response_class=HTMLResponse)
def jade_app():
    path = Path(__file__).resolve().parents[1] / "web" / "index.html"
    return path.read_text(encoding="utf-8")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)

    upload_dir = VAULT / "00-Inbox" / "Attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in file.filename)
    target = upload_dir / safe_name

    counter = 2
    while target.exists():
        target = upload_dir / f"{Path(safe_name).stem} ({counter}){Path(safe_name).suffix}"
        counter += 1

    content = await file.read()
    target.write_bytes(content)

    ingest_result = ingest_attachments()
    file_result = build_file_knowledge()
    index_result = build_typed_indexes()

    return {
        "status": "uploaded_and_processed",
        "filename": target.name,
        "path": str(target),
        "ingest_result": ingest_result,
        "file_intelligence_result": file_result,
        "index_result": index_result,
    }


def _load_chat_history() -> list:
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CHAT_HISTORY_FILE.exists():
        return []
    import json
    return json.loads(CHAT_HISTORY_FILE.read_text(encoding="utf-8"))


def _save_chat_history(items: list) -> None:
    import json
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHAT_HISTORY_FILE.write_text(json.dumps(items[-200:], indent=2), encoding="utf-8")


@app.get("/chat/history")
def chat_history(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"messages": _load_chat_history()}


@app.post("/chat/clear")
def chat_clear(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    _save_chat_history([])
    return {"status": "cleared"}
