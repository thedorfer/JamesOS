from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT

def _link(path: Path) -> str:
    rel = path.relative_to(VAULT).with_suffix("")
    return f"[[{rel.as_posix()}]]"

def _recent(folder: Path, limit: int = 5) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

def _section(title: str, files: list[Path]) -> list[str]:
    lines = ["", f"## {title}"]
    lines.extend([f"- {_link(f)}" for f in files] or ["- None"])
    return lines

def generate_home_dashboard() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    work = VAULT / "Work"
    inbox = VAULT / "00-Inbox"
    daily = VAULT / "Daily"

    active = list((work / "Active Tickets").glob("*.md")) if (work / "Active Tickets").exists() else []
    waiting = list((work / "Waiting").glob("*.md")) if (work / "Waiting").exists() else []
    ready = list((work / "Ready for Testing").glob("*.md")) if (work / "Ready for Testing").exists() else []
    inbox_items = _recent(inbox, 5)
    daily_notes = _recent(daily, 5)

    lines = [
        "# Home",
        "",
        f"Updated: {today}",
        "",
        "## Mission Control",
        "- [[JamesOS/Reports/Daily Briefing]]",
        "- [[JamesOS/Reports/Work Intelligence]]",
        "- [[JamesOS/Reports/Status Report]]",
        "- [[JamesOS/Reports/Inbox Review]]",
        "- [[JamesOS/Reports/AI Inbox Cleanup]]",
        "- [[Work/Work]]",
        "",
        "## Today",
        f"- [[Daily/{today}]]",
        "",
        "## Current Status",
        f"- Active Tickets: {len(active)}",
        f"- Waiting: {len(waiting)}",
        f"- Ready for Testing: {len(ready)}",
        f"- Inbox Items: {len(inbox_items)}",
        "",
        "## Main Areas",
        "- [[Work/Work]]",
        "- [[GCU/GCU Dashboard]]",
        "- [[UnityStitches/UnityStitches Dashboard]]",
        "- [[Personal]]",
        "- [[JamesOS/Knowledge]]",
        "- [[JamesOS/Reports]]",
    ]

    lines += _section("Ready for Testing", sorted(ready))
    lines += _section("Waiting", sorted(waiting))
    lines += _section("Recent Inbox", inbox_items)
    lines += _section("Recent Daily Notes", daily_notes)

    lines.extend([
        "",
        "## Daily Checklist",
        "- [ ] Review Daily Briefing",
        "- [ ] Review Work Intelligence",
        "- [ ] Review Status Report",
        "- [ ] Review AI Inbox Cleanup",
        "- [ ] Clear Inbox captures",
        "- [ ] Update ticket notes",
        "- [ ] Capture loose thoughts",
        "",
    ])

    home = VAULT / "Home.md"
    home.write_text("\n".join(lines), encoding="utf-8")
    return f"Updated {home}"
