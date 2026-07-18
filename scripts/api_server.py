from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from jamesos.core.api import app
from jamesos.core.memory_routes import router as memory_router
from jamesos.services.access_policy import AccessPolicy

app.include_router(memory_router)

policy = AccessPolicy.from_runtime_env()

uvicorn.run(
    app,
    host=policy.bind_host,
    port=8787,
    reload=False,
)
