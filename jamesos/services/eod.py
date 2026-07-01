from datetime import datetime

from jamesos.config import VAULT
from jamesos.services.refresh import refresh_dashboards


def end_day() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    daily_path = VAULT / "Daily" / f"{today}.md"
    daily_path.parent.mkdir(parents=True, exist_ok=True)

    if not daily_path.exists():
        daily_path.write_text(f"# {today}\n\n", encoding="utf-8")

    text = daily_path.read_text(encoding="utf-8")

    marker = f"## End of Day Auto-Close - {today}"

    if marker not in text:
        with daily_path.open("a", encoding="utf-8") as f:
            f.write(
                f"\n{marker}\n"
                f"Closed: {now}\n\n"
                "### Carry Forward\n"
                "- [ ] Review unfinished tasks tomorrow\n\n"
            )

    refresh_dashboards()
    return f"Ended day: {daily_path.relative_to(VAULT)} and refreshed dashboards"
