from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.refresh import refresh_dashboards


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

    refresh_dashboards()
    return f"Started day: {daily_path.relative_to(VAULT)} and refreshed dashboards"
