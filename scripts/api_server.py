from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
root_text = str(ROOT)
# Direct script execution puts scripts/ first. PYTHONPATH may also put the
# repository root later, so membership alone is not sufficient: remove every
# duplicate and make the package root the first import location.
sys.path[:] = [entry for entry in sys.path if entry != root_text]
sys.path.insert(0, root_text)

import uvicorn

from jamesos.core.api import app
from jamesos.core.memory_routes import router as memory_router
from jamesos.services.access_policy import AccessPolicy

if os.environ.get("JAMESOS_API_IMPORT_CHECK") == "1":
    package = sys.modules.get("jamesos")
    print(Path(package.__file__).resolve())
    raise SystemExit(0)

app.include_router(memory_router)

policy = AccessPolicy.from_runtime_env()

uvicorn.run(
    app,
    host=policy.bind_host,
    port=8787,
    reload=False,
)
