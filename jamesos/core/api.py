from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job
from jamesos.services.search_service import search_notes_index
from jamesos.services.status_report import generate_status_report
from jamesos.services.briefing import generate_daily_briefing
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled

API_KEY_FILE = VAULT / "JamesOS" / "Secrets" / "api_key.txt"

app = FastAPI(title="JamesOS API")


class IntakeRequest(BaseModel):
    title: str
    content: str
    source: str = "api"
    source_detail: str = ""


class AskRequest(BaseModel):
    question: str
    use_ai: bool = True


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

    result = enqueue_job("intake", {
        "title": req.title,
        "content": req.content,
        "source": req.source,
        "source_detail": req.source_detail,
    })
    return {"result": result}


@app.get("/search")
def search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": search_notes_index(q)}


@app.post("/ask")
def ask(req: AskRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)

    context_result = build_context_report(req.question, use_ai=False)

    context_file = VAULT / "JamesOS" / "Reports" / "Context" / f"{''.join(c if c.isalnum() or c in ' -_' else '-' for c in req.question)[:80]}.md"
    context_text = context_file.read_text(encoding="utf-8", errors="ignore") if context_file.exists() else context_result

    if req.use_ai and ollama_enabled():
        prompt = (
            "You are JamesOS, James's private assistant. "
            "Answer the question using only the context below. "
            "Be concise and practical. If the answer is not in the context, say so.\n\n"
            f"Question: {req.question}\n\n"
            f"Context:\n{context_text[:12000]}"
        )
        answer = ask_ollama(prompt)
    else:
        answer = context_text[:4000]

    return {
        "question": req.question,
        "answer": answer,
        "context_report": context_result,
    }


@app.get("/daily-briefing")
def daily_briefing(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_daily_briefing()}


@app.get("/status-report")
def status_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_status_report()}
