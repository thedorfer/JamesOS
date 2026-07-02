import uvicorn

uvicorn.run(
    "jamesos.core.api:app",
    host="0.0.0.0",
    port=8787,
    reload=False,
)
