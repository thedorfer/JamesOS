from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT


def _link(path: Path) -> str:
    return f"[[{path.relative_to(VAULT).with_suffix('').as_posix()}]]"


def _files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def generate_work_intelligence() -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    work = VAULT / "Work"
    reports = VAULT / "JamesOS" / "Reports"
    reports.mkdir(parents=True, exist_ok=True)

    active = _files(work / "Active Tickets")
    waiting = _files(work / "Waiting")
    ready = _files(work / "Ready for Testing")
    completed = _files(work / "Completed")[:10]
    meetings = _files(work / "Meetings")[:10]
    deployments = _files(work / "Deployments")[:10]

    lines = [
        "# Work Intelligence",
        "",
        f"Updated: {today}",
        "",
        "## Summary",
        f"- Active Tickets: {len(active)}",
        f"- Waiting: {len(waiting)}",
        f"- Ready for Testing: {len(ready)}",
        f"- Recently Completed: {len(completed)}",
        "",
        "## What Needs Attention",
    ]

    if waiting:
        lines.append("- Waiting items need follow-up.")
    if ready:
        lines.append("- Ready for Testing items may need tester coordination.")
    if not waiting and not ready and not active:
        lines.append("- No active work items found.")

    lines.extend(["", "## Ready for Testing"])
    lines.extend([f"- {_link(p)}" for p in ready] or ["- None"])

    lines.extend(["", "## Waiting"])
    lines.extend([f"- {_link(p)}" for p in waiting] or ["- None"])

    lines.extend(["", "## Active Tickets"])
    lines.extend([f"- {_link(p)}" for p in active] or ["- None"])

    lines.extend(["", "## Recent Meetings"])
    lines.extend([f"- {_link(p)}" for p in meetings] or ["- None"])

    lines.extend(["", "## Recent Deployments"])
    lines.extend([f"- {_link(p)}" for p in deployments] or ["- None"])

    lines.extend(["", "## Suggested Actions"])
    if ready:
        lines.append("- [ ] Check whether ready-for-testing tickets have a tester assigned.")
    if waiting:
        lines.append("- [ ] Follow up on waiting items.")
    if active:
        lines.append("- [ ] Update active ticket notes.")
    lines.append("- [ ] Refresh dashboards before stopping work.")

    path = reports / "Work Intelligence.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Wrote work intelligence report: {path.relative_to(VAULT)}"
