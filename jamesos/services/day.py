from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.refresh import refresh_dashboards
from jamesos.services.relationship_engine import build_internal_db
from jamesos.services.knowledge_service import update_knowledge_pages
from jamesos.services.timeline import build_timeline
from jamesos.services.search_service import build_search_index


def start_day() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    daily_path = VAULT / "Daily" / f"{today}.md"
    daily_path.parent.mkdir(parents=True, exist_ok=True)

    if not daily_path.exists():
        daily_path.write_text(
            f"""# {today}

## Start of Day

## Top Priorities
- [ ] 

## Work
- [[Work/Work]]

## GCU
- [[GCU/GCU Dashboard]]

## UnityStitches
- [[UnityStitches/UnityStitches Dashboard]]

## Personal

## Notes

## End of Day

""",
            encoding="utf-8",
        )

    build_internal_db()
    update_knowledge_pages()
    build_timeline()
    build_search_index()
    refresh_dashboards()
    return f"Started day: {daily_path.relative_to(VAULT)}, rebuilt internal database, updated knowledge pages, built timeline, built search index, and refreshed dashboards"
