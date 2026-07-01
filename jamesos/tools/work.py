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
Customer: {customer}
Status: {status}
Environment: {environment}
Schema: {schema}
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
