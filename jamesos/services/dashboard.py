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
    if files:
        lines.extend(f"- {_link(f)}" for f in files)
    else:
        lines.append("- None")
    return lines

def generate_home_dashboard() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    daily_dir = VAULT / "Daily"
    inbox_dir = VAULT / "00-Inbox"
    work_dir = VAULT / "Work"

    active_dir = work_dir / "Active Tickets"
    waiting_dir = work_dir / "Waiting"
    ready_dir = work_dir / "Ready for Testing"
    completed_dir = work_dir / "Completed"

    active = list(active_dir.glob("*.md")) if active_dir.exists() else []
    waiting = list(waiting_dir.glob("*.md")) if waiting_dir.exists() else []
    ready = list(ready_dir.glob("*.md")) if ready_dir.exists() else []
    completed = _recent(completed_dir, 5)

    recent_daily = _recent(daily_dir, 5)
    recent_inbox = _recent(inbox_dir, 5)

    lines = [
        "# Home",
        "",
        f"Updated: {today}",
        "",
        "## Today",
        f"- [[Daily/{today}]]",
        "- [[Work/Work]]",
        "",
        "## Command Center",
        f"- Active Tickets: {len(active)}",
        f"- Waiting: {len(waiting)}",
        f"- Ready for Testing: {len(ready)}",
        f"- Recent Completed Shown: {len(completed)}",
        f"- Inbox Items Shown: {len(recent_inbox)}",
        "",
        "## Main Areas",
        "- [[Work/Work]]",
        "- [[GCU/GCU Dashboard]]",
        "- [[UnityStitches/UnityStitches Dashboard]]",
        "- [[Personal]]",
        "- [[JamesOS/Knowledge]]",
        "- [[JamesOS/Reports]]",
        "",
        "## Work Status",
        f"- [[Work/Active Tickets]] ({len(active)})",
        f"- [[Work/Waiting]] ({len(waiting)})",
        f"- [[Work/Ready for Testing]] ({len(ready)})",
        f"- [[Work/Completed]]",
    ]

    lines += _section("Ready for Testing", sorted(ready))
    lines += _section("Waiting", sorted(waiting))
    lines += _section("Recent Inbox", recent_inbox)
    lines += _section("Recent Daily Notes", recent_daily)

    lines.extend([
        "",
        "## Daily Checklist",
        "- [ ] Review Work dashboard",
        "- [ ] Review Inbox",
        "- [ ] Check GCU tasks",
        "- [ ] Capture loose notes",
        "- [ ] Update active ticket notes",
        "",
    ])

    home = VAULT / "Home.md"
    home.write_text("\n".join(lines), encoding="utf-8")
    return f"Updated {home}"
