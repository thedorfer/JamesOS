from datetime import datetime

from jamesos.config import VAULT
from jamesos.tools.notes import safe_path


def create_work_ticket(
    ticket_id: str,
    title: str,
    ticket_type: str = "Ticket",
    customer: str = "WGL",
    environment: str = "",
    schema: str = "",
    status: str = "Investigating",
    assigned_to: str = "James",
    tester: str = "",
    notes: str = "",
) -> str:
    from jamesos.services.refresh import refresh_dashboards

    date = datetime.now().strftime("%Y-%m-%d")
    safe_ticket_id = ticket_id.strip()
    safe_title = title.strip() or safe_ticket_id

    path = safe_path(f"Work/Active Tickets/{safe_ticket_id}.md")

    if path.exists():
        return f"Ticket already exists: {path.relative_to(VAULT)}"

    path.parent.mkdir(parents=True, exist_ok=True)

    sql_block = "```sql\n\n```"

    content = f"""# {safe_ticket_id} - {safe_title}

Type: {ticket_type}
Customer: [[JamesOS/Knowledge/Customers/{customer}]]
Status: {status}
Environment: [[JamesOS/Knowledge/Environments/{environment}]]
Schema: [[JamesOS/Knowledge/Systems/{schema}]]
Assigned To: {assigned_to}
Tester: {tester}
Created: {date}

## Summary

{notes}

## Current Status

- [ ] Investigating
- [ ] Code ready
- [ ] Deployed to DEV/SFM2
- [ ] Deployed to SBX
- [ ] Ready for testing
- [ ] Complete

## Requirements / Acceptance Criteria

## Database Objects

## SQL / Code

{sql_block}

## Testing

## Deployment Notes

## Rollback Notes

## Communication

## Links

"""

    path.write_text(content, encoding="utf-8")
    refresh_dashboards()
    return f"Created {path.relative_to(VAULT)} and refreshed dashboards"


def update_work_ticket_status(ticket_id: str, status: str) -> str:
    from jamesos.services.refresh import refresh_dashboards
    import shutil

    status_clean = status.strip()
    ticket_id_clean = ticket_id.strip()

    folder_map = {
        "active": "Active Tickets",
        "investigating": "Active Tickets",
        "waiting": "Waiting",
        "blocked": "Waiting",
        "ready for testing": "Ready for Testing",
        "ready": "Ready for Testing",
        "testing": "Ready for Testing",
        "complete": "Completed",
        "completed": "Completed",
        "done": "Completed",
    }

    target_folder_name = folder_map.get(status_clean.lower(), "Active Tickets")

    work_dir = VAULT / "Work"
    search_dirs = [
        work_dir / "Active Tickets",
        work_dir / "Waiting",
        work_dir / "Ready for Testing",
        work_dir / "Completed",
    ]

    current_path = None
    for folder in search_dirs:
        candidate = folder / f"{ticket_id_clean}.md"
        if candidate.exists():
            current_path = candidate
            break

    if current_path is None:
        return f"Ticket not found: {ticket_id_clean}"

    text = current_path.read_text(encoding="utf-8")

    lines = text.splitlines()
    updated_lines = []
    replaced = False

    for line in lines:
        if line.startswith("Status:"):
            updated_lines.append(f"Status: {status_clean}")
            replaced = True
        else:
            updated_lines.append(line)

    if not replaced:
        updated_lines.insert(1, f"Status: {status_clean}")

    target_dir = work_dir / target_folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / current_path.name

    current_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    if current_path != target_path:
        shutil.move(str(current_path), str(target_path))

    refresh_dashboards()
    return f"Updated {ticket_id_clean} to {status_clean} and moved to Work/{target_folder_name}"


def append_work_ticket_log(ticket_id: str, note: str) -> str:
    from datetime import datetime
    from jamesos.services.refresh import refresh_dashboards

    ticket_id_clean = ticket_id.strip()
    work_dir = VAULT / "Work"
    search_dirs = [
        work_dir / "Active Tickets",
        work_dir / "Waiting",
        work_dir / "Ready for Testing",
        work_dir / "Completed",
    ]

    ticket_path = None
    for folder in search_dirs:
        candidate = folder / f"{ticket_id_clean}.md"
        if candidate.exists():
            ticket_path = candidate
            break

    if ticket_path is None:
        return f"Ticket not found: {ticket_id_clean}"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with ticket_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## Work Log - {timestamp}\n\n{note.strip()}\n")

    refresh_dashboards()
    return f"Appended work log to {ticket_path.relative_to(VAULT)}"
