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


@app.get("/search")
def search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": search_notes_index(q)}


@app.post("/ask")
def ask(req: AskRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)

    retrieval_query = _search_query_from_question(req.question)
    context_result = build_context_report(retrieval_query, use_ai=False)
    safe = "".join(c if c.isalnum() or c in " -_" else "-" for c in req.question)[:80]
    context_file = VAULT / "JamesOS" / "Reports" / "Context" / f"{safe}.md"
    graph_context = context_file.read_text(encoding="utf-8", errors="ignore") if context_file.exists() else context_result
    search_context = _read_search_context(retrieval_query)

    combined_context = (
        "# Graph Context\n\n"
        + graph_context[:8000]
        + "\n\n---\n\n"
        + search_context[:8000]
    )

    if req.use_ai and ollama_enabled():
        prompt = (
            "You are JamesOS, James's private assistant. "
            "Answer using only the context below. Be concise and practical. "
            "Prefer concrete facts, dates, names, links, and next actions. "
            "If the answer is not in the context, say what is missing.\n\n"
            f"Question: {req.question}\nRetrieval Query: {retrieval_query}\n\n"
            f"Context:\n{combined_context[:14000]}"
        )
        answer = ask_ollama(prompt)
    else:
        answer = combined_context[:6000]

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
