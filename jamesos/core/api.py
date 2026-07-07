from pathlib import Path
from typing import Any
from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job
from jamesos.services.search_service import search_notes_index
from jamesos.services.status_report import generate_status_report
from jamesos.services.briefing import generate_daily_briefing
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.rich_context import build_rich_context
from jamesos.services.agent import ask_agent, handle_jade_message
from jamesos.services.jade_planner import answer_with_planner
from jamesos.services.jade_brain import answer_with_brain, summarize_chat_history
from jamesos.services.jade_reasoner import answer_with_reasoner
from jamesos.services.jade_context_packages import dashboard_cards
from jamesos.services.job_queue import (
    JobQueueError,
    approve_job,
    create_job,
    fail_job,
    get_job,
    list_jobs,
)
from jamesos.services.knowledge_graph import build_knowledge_graph, graph_lookup
from jamesos.services.memory_service import remember, search_memory
from jamesos.services.typed_index import build_typed_indexes, search_typed_indexes
from jamesos.services.tool_router import route_tool
from jamesos.services.attachment_ingest import ingest_attachments
from jamesos.services.attachment_processor import process_pending_attachment_jobs
from jamesos.services.file_intelligence import build_file_knowledge
from jamesos.services.phone_ingest import ingest_phone_event, ingest_phone_events, phone_daily_summary
from jamesos.services.creative_studio import (
    approve_creative_job,
    create_creative_job,
    fail_creative_job,
    get_creative_job,
    health as creative_studio_health,
    list_creative_jobs,
)
from jamesos.services.server_config import (
    integration_health,
    server_config,
    service_health,
    write_server_config_report,
)

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
    mode: str = "personal"


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


class JobCreateRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    requires_approval: bool = True
    steps: list[str | dict[str, Any]] = Field(default_factory=list)


class JobFailRequest(BaseModel):
    reason: str = ""


class CreativeJobCreateRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5


class PhoneEventRequest(BaseModel):
    type: str = "notification"
    device: str = "android"
    timestamp: str = ""
    person: str = ""
    number: str = ""
    direction: str = ""
    app: str = ""
    text: str = ""
    title: str = ""
    body: str = ""
    package: str = ""
    duration: str = ""


class PhoneBatchRequest(BaseModel):
    events: list[dict[str, Any]]


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


@app.post("/phone-ingest")
def phone_ingest(req: PhoneEventRequest | PhoneBatchRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    data = req.model_dump()
    if "events" in data:
        return ingest_phone_events(data["events"])
    return ingest_phone_event(data)


@app.post("/phone/daily-summary")
def phone_summary(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "report": phone_daily_summary()}


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

    result = answer_with_reasoner(req.question, use_ai=req.use_ai, mode=req.mode)

    history = _load_chat_history()
    history.append({
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "question": req.question,
        "mode": req.mode,
        "answer": result.get("answer", ""),
        "action": result.get("action", ""),
    })
    _save_chat_history(history)
    return result


@app.get("/ask")
def ask_get(q: str, use_ai: bool = True, mode: str = "personal", x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return answer_with_reasoner(q, use_ai=use_ai, mode=mode)


@app.get("/dashboard")
def dashboard(mode: str = "personal", x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return dashboard_cards(mode)


@app.get("/server/config")
def server_config_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "server": server_config(), "integrations": integration_health()}


@app.get("/server/health")
def server_health(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return service_health()


@app.get("/server/page")
def server_config_page(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return write_server_config_report()


@app.get("/jobs")
def jobs(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "jobs": list_jobs(status)}
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs/{job_id}")
def job_detail(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs")
def job_create(req: JobCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return create_job(
        req.type,
        req.payload,
        priority=req.priority,
        requires_approval=req.requires_approval,
        steps=req.steps,
    )


@app.post("/jobs/{job_id}/approve")
def job_approve(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return approve_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/fail")
def job_fail(job_id: str, req: JobFailRequest | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return fail_job(job_id, reason=req.reason if req else "")
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/creative-studio/health")
def creative_studio_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return creative_studio_health()


@app.get("/creative-studio/jobs")
def creative_studio_jobs(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "jobs": list_creative_jobs(status)}
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creative-studio/jobs")
def creative_studio_job_create(req: CreativeJobCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return create_creative_job(req.type, req.payload, priority=req.priority)
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/creative-studio/jobs/{job_id}")
def creative_studio_job_detail(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_creative_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/creative-studio/jobs/{job_id}/approve")
def creative_studio_job_approve(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return approve_creative_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/creative-studio/jobs/{job_id}/fail")
def creative_studio_job_fail(job_id: str, req: JobFailRequest | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return fail_creative_job(job_id, reason=req.reason if req else "")
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    return search_memory(q)


@app.get("/graph/search")
def graph_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return graph_lookup(q)


@app.post("/graph/build")
def graph_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_knowledge_graph()}


@app.get("/typed/search")
def typed_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return search_typed_indexes(q)


@app.post("/typed/build")
def typed_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_typed_indexes()}


@app.post("/brain/summarize-chat")
def brain_summarize_chat(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": summarize_chat_history()}


@app.post("/attachments/ingest")
def attachments_ingest(files: list[UploadFile] = File(...), x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return ingest_attachments(files)


@app.post("/attachments/process-pending")
def attachments_process_pending(limit: int = 10, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return process_pending_attachment_jobs(limit=limit)


@app.post("/files/build")
def files_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_file_knowledge()}


@app.get("/")
def index():
    return HTMLResponse("<h1>JamesOS API</h1><p>Service is running.</p>")


def _load_chat_history() -> list[dict]:
    import json
    if not CHAT_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(CHAT_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_chat_history(history: list[dict]) -> None:
    import json
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHAT_HISTORY_FILE.write_text(json.dumps(history[-500:], indent=2), encoding="utf-8")
