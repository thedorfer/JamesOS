from fastapi import FastAPI
from pydantic import BaseModel

from jamesos.core.queue import enqueue_job
from jamesos.services.search_service import search_notes_index
from jamesos.services.status_report import generate_status_report
from jamesos.services.briefing import generate_daily_briefing

app = FastAPI(title="JamesOS API")


class IntakeRequest(BaseModel):
    title: str
    content: str
    source: str = "api"
    source_detail: str = ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "JamesOS"}


@app.post("/intake")
def intake(req: IntakeRequest):
    result = enqueue_job("intake", {
        "title": req.title,
        "content": req.content,
        "source": req.source,
        "source_detail": req.source_detail,
    })
    return {"result": result}


@app.get("/search")
def search(q: str):
    return {"result": search_notes_index(q)}


@app.get("/daily-briefing")
def daily_briefing():
    return {"result": generate_daily_briefing()}


@app.get("/status-report")
def status_report():
    return {"result": generate_status_report()}
