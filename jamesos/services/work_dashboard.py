from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT

def _link(path: Path) -> str:
    rel = path.relative_to(VAULT).with_suffix("")
    return f"[[{rel.as_posix()}]]"

def _section(title: str, files: list[Path]) -> list[str]:
    lines = ["", f"## {title}"]
    if files:
        lines.extend(f"- {_link(f)}" for f in files)
    else:
        lines.append("- None")
    return lines

def generate_work_dashboard() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    work_dir = VAULT / "Work"
    folders = {
        "Active Tickets": work_dir / "Active Tickets",
        "Waiting": work_dir / "Waiting",
        "Ready for Testing": work_dir / "Ready for Testing",
        "Completed": work_dir / "Completed",
        "Meetings": work_dir / "Meetings",
        "Deployments": work_dir / "Deployments",
        "SQL Snippets": work_dir / "SQL Snippets",
    }

    for folder in folders.values():
        folder.mkdir(parents=True, exist_ok=True)

    active = sorted(folders["Active Tickets"].glob("*.md"))
    waiting = sorted(folders["Waiting"].glob("*.md"))
    ready = sorted(folders["Ready for Testing"].glob("*.md"))
    completed = sorted(folders["Completed"].glob("*.md"), reverse=True)[:10]
    meetings = sorted(folders["Meetings"].glob("*.md"), reverse=True)[:10]
    deployments = sorted(folders["Deployments"].glob("*.md"), reverse=True)[:10]
    sql_notes = sorted(folders["SQL Snippets"].glob("*.md"))[:20]

    lines = [
        "# Work",
        "",
        f"Updated: {today}",
        "",
        "## Quick Links",
        "- [[Work/Active Tickets]]",
        "- [[Work/Waiting]]",
        "- [[Work/Ready for Testing]]",
        "- [[Work/Completed]]",
        "- [[Work/Meetings]]",
        "- [[Work/Deployments]]",
        "- [[Work/SQL Snippets]]",
    ]

    lines += _section("Active Tickets", active)
    lines += _section("Waiting", waiting)
    lines += _section("Ready for Testing", ready)
    lines += _section("Recently Completed", completed)
    lines += _section("Recent Meetings", meetings)
    lines += _section("Recent Deployments", deployments)
    lines += _section("SQL Snippets", sql_notes)

    lines.extend([
        "",
        "## Work Checklist",
        "- [ ] Review active tickets",
        "- [ ] Check waiting items",
        "- [ ] Check ready-for-testing items",
        "- [ ] Update ticket notes before end of day",
        "- [ ] Sync notes",
        "",
    ])

    dashboard = work_dir / "Work.md"
    dashboard.write_text("\n".join(lines), encoding="utf-8")
    return f"Updated {dashboard}"
