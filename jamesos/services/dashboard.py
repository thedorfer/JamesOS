from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT

def _link(path: Path) -> str:
    rel = path.relative_to(VAULT).with_suffix("")
    return f"[[{rel.as_posix()}]]"

def generate_home_dashboard() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    active_tickets_dir = VAULT / "Work" / "Active Tickets"
    daily_dir = VAULT / "Daily"

    tickets = sorted(active_tickets_dir.glob("*.md")) if active_tickets_dir.exists() else []
    daily_notes = sorted(daily_dir.glob("*.md"), reverse=True)[:5] if daily_dir.exists() else []

    lines = [
        "# Home",
        "",
        f"Updated: {today}",
        "",
        "## Main Areas",
        "- [[GCU/GCU Dashboard]]",
        "- [[UnityStitches/UnityStitches Dashboard]]",
        "- [[Work]]",
        "- [[Personal]]",
        "",
        "## Today",
        f"- [[Daily/{today}]]",
        "",
        "## Active Tickets",
    ]

    if tickets:
        lines.extend(f"- {_link(t)}" for t in tickets)
    else:
        lines.append("- No active tickets found.")

    lines.extend([
        "",
        "## Recent Daily Notes",
    ])

    if daily_notes:
        lines.extend(f"- {_link(d)}" for d in daily_notes)
    else:
        lines.append("- No daily notes found.")

    lines.extend([
        "",
        "## Inbox",
        "- [[00-Inbox]]",
        "",
        "## This Week",
        "- [ ] Review GCU tasks",
        "- [ ] Review UnityStitches ideas",
        "- [ ] Clean up inbox notes",
        "",
    ])

    home = VAULT / "Home.md"
    home.write_text("\n".join(lines), encoding="utf-8")
    return f"Updated {home}"
