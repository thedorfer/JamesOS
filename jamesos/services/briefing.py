from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT


def _link(path: Path) -> str:
    return f"[[{path.relative_to(VAULT).with_suffix('').as_posix()}]]"


def generate_daily_briefing() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    work = VAULT / "Work"
    inbox = VAULT / "00-Inbox"
    reports = VAULT / "JamesOS" / "Reports"
    reports.mkdir(parents=True, exist_ok=True)

    ready = sorted((work / "Ready for Testing").glob("*.md")) if (work / "Ready for Testing").exists() else []
    waiting = sorted((work / "Waiting").glob("*.md")) if (work / "Waiting").exists() else []
    active = sorted((work / "Active Tickets").glob("*.md")) if (work / "Active Tickets").exists() else []
    inbox_items = sorted(inbox.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if inbox.exists() else []

    lines = [
        "# Daily Briefing",
        "",
        f"Date: {today}",
        "",
        "## Work Snapshot",
        f"- Active Tickets: {len(active)}",
        f"- Waiting: {len(waiting)}",
        f"- Ready for Testing: {len(ready)}",
        f"- Inbox Items: {len(inbox_items)}",
        "",
        "## Ready for Testing",
    ]

    lines.extend([f"- {_link(p)}" for p in ready] or ["- None"])

    lines.extend(["", "## Waiting"])
    lines.extend([f"- {_link(p)}" for p in waiting] or ["- None"])

    lines.extend(["", "## Active Tickets"])
    lines.extend([f"- {_link(p)}" for p in active] or ["- None"])

    lines.extend(["", "## Inbox Review"])
    lines.extend([f"- {_link(p)}" for p in inbox_items[:10]] or ["- Inbox is clear"])

    lines.extend([
        "",
        "## Suggested Priorities",
        "- [ ] Review Ready for Testing tickets",
        "- [ ] Review Waiting items",
        "- [ ] Clear Inbox captures",
        "- [ ] Update active ticket notes",
        "",
    ])

    path = reports / "Daily Briefing.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote daily briefing: {path.relative_to(VAULT)}"
