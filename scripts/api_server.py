import uvicorn

from jamesos.core.api import app
from jamesos.core.memory_routes import router as memory_router

app.include_router(memory_router)

uvicorn.run(
    app,
    host="0.0.0.0",
    port=8787,
    reload=False,
)
