from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT


def _link(path: Path) -> str:
    return f"[[{path.relative_to(VAULT).with_suffix('').as_posix()}]]"


def _files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def generate_status_report() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    work = VAULT / "Work"
    reports = VAULT / "JamesOS" / "Reports"
    reports.mkdir(parents=True, exist_ok=True)

    active = _files(work / "Active Tickets")
    waiting = _files(work / "Waiting")
    ready = _files(work / "Ready for Testing")
    completed = _files(work / "Completed")[:10]
    meetings = _files(work / "Meetings")[:5]

    lines = [
        "# Status Report",
        "",
        f"Generated: {now}",
        "",
        "## Summary",
        f"- Active Tickets: {len(active)}",
        f"- Waiting: {len(waiting)}",
        f"- Ready for Testing: {len(ready)}",
        f"- Recently Completed: {len(completed)}",
        "",
        "## Ready for Testing",
    ]

    lines.extend([f"- {_link(p)}" for p in ready] or ["- None"])

    lines.extend(["", "## Waiting / Blocked"])
    lines.extend([f"- {_link(p)}" for p in waiting] or ["- None"])

    lines.extend(["", "## Active Work"])
    lines.extend([f"- {_link(p)}" for p in active] or ["- None"])

    lines.extend(["", "## Recently Completed"])
    lines.extend([f"- {_link(p)}" for p in completed] or ["- None"])

    lines.extend(["", "## Recent Meetings"])
    lines.extend([f"- {_link(p)}" for p in meetings] or ["- None"])

    lines.extend([
        "",
        "## Draft Update Message",
        "",
        "Good Morning,",
        "",
        f"Current status: {len(ready)} ready for testing, {len(waiting)} waiting/blocked, and {len(active)} active/in progress.",
        "",
    ])

    if ready:
        lines.append("Ready for testing:")
        lines.extend(f"- {p.stem}" for p in ready)
        lines.append("")

    if waiting:
        lines.append("Waiting/blocked:")
        lines.extend(f"- {p.stem}" for p in waiting)
        lines.append("")

    if active:
        lines.append("Active/in progress:")
        lines.extend(f"- {p.stem}" for p in active)
        lines.append("")

    lines.extend([
        "Thanks,",
        "James",
        "",
    ])

    path = reports / "Status Report.md"
    path.write_text("\n".join(lines), encoding="utf-8")

    return f"Wrote status report: {path.relative_to(VAULT)}"
