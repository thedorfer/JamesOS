import json
import re
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.relationship_engine import build_internal_db

INBOX_DIR = VAULT / "00-Inbox"
REPORTS_DIR = VAULT / "JamesOS" / "Reports"
ENTITIES_FILE = VAULT / "JamesOS" / "Index" / "entities.json"


def _load_entities() -> dict:
    if not ENTITIES_FILE.exists():
        build_internal_db()
    return json.loads(ENTITIES_FILE.read_text(encoding="utf-8"))


def _entity_matches(text: str, entities: dict) -> list[str]:
    matches = []
    lower = text.lower()

    for category, items in entities.get("entities", {}).items():
        for name in items.keys():
            if re.search(r"\b" + re.escape(name.lower()) + r"\b", lower):
                matches.append(f"{name} ({category})")

    for ticket in entities.get("tickets", {}).keys():
        if ticket in text:
            matches.append(f"{ticket} (Ticket)")

    return sorted(set(matches))


def _suggest_destination(matches: list[str], text: str) -> str:
    joined = " ".join(matches).lower()
    lower = text.lower()

    if "ticket" in joined or re.search(r"\b\d{5}\b", lower):
        return "Work / Ticket Update"

    if any(word in lower for word in ["meeting", "call", "discussed", "talked"]):
        return "Work / Meeting Note"

    if any(word in lower for word in ["gcu", "student", "grade", "rubric", "class"]):
        return "GCU"

    if any(word in lower for word in ["etsy", "commerce_shop", "shirt", "design", "listing"]):
        return "Commerce Shop"

    if any(word in lower for word in ["trip", "hotel", "flight", "family", "school"]):
        return "Personal"

    return "Needs Review"


def review_inbox() -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    entities = _load_entities()

    inbox_files = sorted(INBOX_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    lines = [
        "# Inbox Review",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Items reviewed: {len(inbox_files)}",
        "",
    ]

    if not inbox_files:
        lines.append("No inbox items found.")
    else:
        for path in inbox_files:
            rel = path.relative_to(VAULT).with_suffix("").as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")

            matches = _entity_matches(text, entities)
            suggestion = _suggest_destination(matches, text)

            lines.extend([
                f"## [[{rel}]]",
                f"Suggested Destination: {suggestion}",
                "",
                "Matched Entities:",
            ])

            if matches:
                lines.extend(f"- {m}" for m in matches)
            else:
                lines.append("- None")

            lines.extend([
                "",
                "Suggested Actions:",
                "- [ ] Review item",
                "- [ ] Decide destination",
                "- [ ] Process or archive",
                "",
            ])

    report = REPORTS_DIR / "Inbox Review.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    return f"Wrote inbox review: {report.relative_to(VAULT)}"
