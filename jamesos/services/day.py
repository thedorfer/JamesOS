from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.refresh import refresh_dashboards
from jamesos.services.database import build_database
from jamesos.services.knowledge_service import update_knowledge_pages
from jamesos.services.timeline import build_timeline
from jamesos.services.search_service import build_search_index
from jamesos.services.inbox_review import review_inbox


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

    build_database()
    update_knowledge_pages()
    build_timeline()
    build_search_index()
    review_inbox()
    refresh_dashboards()
    return f"Started day: {daily_path.relative_to(VAULT)}, rebuilt JamesOS database, updated knowledge pages, built timeline, built search index, reviewed inbox, and refreshed dashboards"
