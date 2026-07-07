from __future__ import annotations

from fastapi import FastAPI

from creative_intelligence.routes import etsy, ideas, products, prompts, trends
from creative_intelligence.storage.sqlite import init_db


app = FastAPI(title="JamesOS Creative Intelligence")

app.include_router(trends.router)
app.include_router(ideas.router)
app.include_router(prompts.router)
app.include_router(products.router)
app.include_router(etsy.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "creative_intelligence", **init_db()}
