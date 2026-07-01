from pathlib import Path
from datetime import datetime
import shutil

from jamesos.config import VAULT

def safe_path(rel_path: str) -> Path:
    path = (VAULT / rel_path).resolve()
    if not str(path).startswith(str(VAULT)):
        raise ValueError("Path is outside the vault")
    return path

def list_notes(folder: str = ".") -> list[str]:
    path = safe_path(folder)
    return sorted(str(p.relative_to(VAULT)) for p in path.rglob("*.md"))

def read_note(path: str) -> str:
    return safe_path(path).read_text(encoding="utf-8")

def write_note(path: str, content: str) -> str:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {target.relative_to(VAULT)}"

def append_note(path: str, content: str) -> str:
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write("\n" + content.strip() + "\n")
    return f"Appended to {target.relative_to(VAULT)}"

def search_notes(query: str) -> list[str]:
    q = query.lower()
    results = []
    for p in VAULT.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8").lower()
            if q in text or q in p.name.lower():
                results.append(str(p.relative_to(VAULT)))
        except Exception:
            continue
    return sorted(results)

def create_daily_note() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    path = safe_path(f"Daily/{today}.md")
    if path.exists():
        return f"Daily note already exists: {path.relative_to(VAULT)}"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {today}\n\n"
        "## Today\n- [ ] Review priorities\n\n"
        "## Work\n\n"
        "## GCU\n\n"
        "## Personal\n\n"
        "## Notes\n",
        encoding="utf-8",
    )
    return f"Created {path.relative_to(VAULT)}"

def create_ticket(ticket_id: str, title: str = "") -> str:
    safe_title = title.strip() or f"Ticket {ticket_id}"
    path = safe_path(f"Work/Active Tickets/{ticket_id}.md")
    if path.exists():
        return f"Ticket already exists: {path.relative_to(VAULT)}"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {ticket_id} - {safe_title}\n\n"
        "## Summary\n\n"
        "## Status\n- [ ] Investigating\n\n"
        "## Requirements\n\n"
        "## SQL / Code\n\n```sql\n\n```\n\n"
        "## Testing\n\n"
        "## Deployment Notes\n\n"
        "## Communication\n\n"
        "## Links\n",
        encoding="utf-8",
    )
    return f"Created {path.relative_to(VAULT)}"

def create_meeting_note(title: str, folder: str = "Work/Meetings") -> str:
    from jamesos.services.refresh import refresh_dashboards

    date = datetime.now().strftime("%Y-%m-%d")
    clean_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    path = safe_path(f"{folder}/{date} - {clean_title}.md")

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return f"Meeting note already exists: {path.relative_to(VAULT)}"

    path.write_text(
        f"# {title}\n\n"
        f"Date: {date}\n\n"
        "## Attendees\n\n"
        "## Topics\n\n"
        "## Notes\n\n"
        "## Action Items\n- [ ] \n",
        encoding="utf-8",
    )

    refresh_dashboards()
    return f"Created {path.relative_to(VAULT)} and refreshed dashboards"

def move_note(source: str, destination: str) -> str:
    src = safe_path(source)
    dst = safe_path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Moved {source} to {destination}"
