import json
import re
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.database import build_database

DATABASE_FILE = VAULT / "JamesOS" / "Database" / "jamesos_db.json"
INBOX_DIR = VAULT / "00-Inbox"
REPORTS_DIR = VAULT / "JamesOS" / "Reports"


def _load_db() -> dict:
    if not DATABASE_FILE.exists():
        build_database()
    return json.loads(DATABASE_FILE.read_text(encoding="utf-8"))


def _extract_known_entities(text: str, db: dict) -> list[str]:
    found = []
    lower = text.lower()

    entities = db.get("entities", {}).get("entities", {})

    for category, items in entities.items():
        for name in items.keys():
            if re.search(r"\\b" + re.escape(name.lower()) + r"\\b", lower):
                found.append(f"{name} ({category})")

    for ticket in db.get("entities", {}).get("tickets", {}).keys():
        if ticket in text:
            found.append(f"{ticket} (Ticket)")

    return sorted(set(found))


def _suggest_actions(text: str, entities: list[str]) -> list[str]:
    lower = text.lower()
    actions = []

    ticket_matches = [e for e in entities if "(Ticket)" in e]

    if ticket_matches:
        ticket = ticket_matches[0].split(" ")[0]
        actions.append(f"Append this capture to ticket {ticket}.")
        actions.append(f"Consider updating ticket {ticket} status if the note indicates waiting, ready, blocked, or complete.")

    if any(word in lower for word in ["meeting", "call", "talked", "discussed"]):
        actions.append("Consider creating a meeting note.")

    if any(word in lower for word in ["waiting", "blocked", "need kevin", "need tom", "follow up"]):
        actions.append("Possible waiting/follow-up item.")

    if any(word in lower for word in ["deploy", "deployed", "migration", "package", "rollback"]):
        actions.append("Possible deployment note.")

    if any(word in lower for word in ["gcu", "student", "grade", "rubric", "class"]):
        actions.append("Possible GCU item.")

    if any(word in lower for word in ["etsy", "unitystitches", "design", "listing", "shirt"]):
        actions.append("Possible UnityStitches item.")

    if any(word in lower for word in ["trip", "travel", "hotel", "flight", "reservation"]):
        actions.append("Possible personal/travel item.")

    if not actions:
        actions.append("Needs manual review.")

    return actions


def suggest_inbox_cleanup() -> str:
    db = _load_db()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(INBOX_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if INBOX_DIR.exists() else []

    lines = [
        "# AI Inbox Cleanup Suggestions",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Mode: suggestions only. No files were changed.",
        "",
        f"Items reviewed: {len(files)}",
        "",
    ]

    if not files:
        lines.append("Inbox is clear.")
    else:
        for path in files:
            rel = path.relative_to(VAULT).with_suffix("").as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")

            entities = _extract_known_entities(text, db)
            actions = _suggest_actions(text, entities)

            lines.extend([
                f"## [[{rel}]]",
                "",
                "Matched Entities:",
            ])

            lines.extend([f"- {e}" for e in entities] or ["- None"])

            lines.extend(["", "Suggested Actions:"])
            lines.extend([f"- [ ] {a}" for a in actions])

            lines.extend(["", "Suggested Safety:", "- [ ] Review before applying", ""])

    report = REPORTS_DIR / "AI Inbox Cleanup.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote AI inbox cleanup suggestions: {report.relative_to(VAULT)}"
