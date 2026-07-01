from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT

def _link(path: Path) -> str:
    rel = path.relative_to(VAULT).with_suffix("")
    return f"[[{rel.as_posix()}]]"

def generate_work_dashboard() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    work_dir = VAULT / "Work"
    active_tickets_dir = work_dir / "Active Tickets"
    meetings_dir = work_dir / "Meetings"
    deployments_dir = work_dir / "Deployments"
    sql_dir = work_dir / "SQL Snippets"

    work_dir.mkdir(parents=True, exist_ok=True)
    active_tickets_dir.mkdir(parents=True, exist_ok=True)
    meetings_dir.mkdir(parents=True, exist_ok=True)
    deployments_dir.mkdir(parents=True, exist_ok=True)
    sql_dir.mkdir(parents=True, exist_ok=True)

    tickets = sorted(active_tickets_dir.glob("*.md"))
    meetings = sorted(meetings_dir.glob("*.md"), reverse=True)[:10]
    deployments = sorted(deployments_dir.glob("*.md"), reverse=True)[:10]
    sql_notes = sorted(sql_dir.glob("*.md"))[:20]

    lines = [
        "# Work",
        "",
        f"Updated: {today}",
        "",
        "## Quick Links",
        "- [[Work/Active Tickets]]",
        "- [[Work/Meetings]]",
        "- [[Work/Deployments]]",
        "- [[Work/SQL Snippets]]",
        "",
        "## Active Tickets",
    ]

    if tickets:
        lines.extend(f"- {_link(t)}" for t in tickets)
    else:
        lines.append("- No active tickets found.")

    lines.extend([
        "",
        "## Recent Meetings",
    ])

    if meetings:
        lines.extend(f"- {_link(m)}" for m in meetings)
    else:
        lines.append("- No meeting notes found.")

    lines.extend([
        "",
        "## Recent Deployments",
    ])

    if deployments:
        lines.extend(f"- {_link(d)}" for d in deployments)
    else:
        lines.append("- No deployment notes found.")

    lines.extend([
        "",
        "## SQL Snippets",
    ])

    if sql_notes:
        lines.extend(f"- {_link(s)}" for s in sql_notes)
    else:
        lines.append("- No SQL snippets found.")

    lines.extend([
        "",
        "## Work Checklist",
        "- [ ] Review active tickets",
        "- [ ] Check pending deployments",
        "- [ ] Update ticket notes before end of day",
        "- [ ] Sync notes",
        "",
    ])

    dashboard = work_dir / "Work.md"
    dashboard.write_text("\n".join(lines), encoding="utf-8")
    return f"Updated {dashboard}"
