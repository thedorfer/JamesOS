from datetime import datetime

from jamesos.config import VAULT


def start_day() -> str:
    from jamesos.services.job_engine import start_day_job

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

## Commerce Shop
- [[Commerce Shop/Commerce Shop Dashboard]]

## Personal

## Notes

## End of Day

""",
            encoding="utf-8",
        )

    result = start_day_job()
    return f"Started day: {daily_path.relative_to(VAULT)}\n{result}"
