from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
