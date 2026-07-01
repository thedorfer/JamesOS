import json
from datetime import datetime

from jamesos.config import VAULT
from jamesos.services.relationship_engine import build_internal_db
from jamesos.services.timeline import build_timeline
from jamesos.services.search_service import build_search_index

INDEX_ROOT = VAULT / "JamesOS" / "Index"
DATABASE_ROOT = VAULT / "JamesOS" / "Database"
DATABASE_FILE = DATABASE_ROOT / "jamesos_db.json"


def _load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_database() -> str:
    DATABASE_ROOT.mkdir(parents=True, exist_ok=True)

    build_internal_db()
    build_timeline()
    build_search_index()

    db = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "vault": str(VAULT),
        "entities": _load_json(INDEX_ROOT / "entities.json"),
        "relationships": _load_json(INDEX_ROOT / "relationships.json"),
        "timeline": _load_json(INDEX_ROOT / "timeline.json"),
        "search": _load_json(INDEX_ROOT / "search.json"),
    }

    DATABASE_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")

    return f"Built JamesOS database: {DATABASE_FILE.relative_to(VAULT)}"
