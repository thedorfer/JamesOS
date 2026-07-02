import json
from datetime import datetime, date
from pathlib import Path

from jamesos.config import VAULT
from jamesos.config.loader import get_config

PEOPLE_ROOT = VAULT / "JamesOS" / "People"
REPORTS = VAULT / "JamesOS" / "Reports"
GOOGLE_CONTACTS_FILE = VAULT / "JamesOS" / "Database" / "google_contacts" / "contacts.json"


def _days_until(date_text: str) -> int | None:
    if not date_text:
        return None
    try:
        month, day = map(int, date_text.split("-")[-2:])
    except Exception:
        return None

    today = date.today()
    target = date(today.year, month, day)
    if target < today:
        target = date(today.year + 1, month, day)
    return (target - today).days


def _load_people() -> dict:
    people = {}

    manual = get_config("contacts.yaml").get("contacts", {}).get("people", {})
    for name, info in manual.items():
        people[name] = dict(info)
        people[name]["source"] = people[name].get("source", "manual")

    if GOOGLE_CONTACTS_FILE.exists():
        google = json.loads(GOOGLE_CONTACTS_FILE.read_text(encoding="utf-8")).get("contacts", {})
        for name, info in google.items():
            people.setdefault(name, {})
            for key, value in info.items():
                if value and not people[name].get(key):
                    people[name][key] = value
            people[name]["source"] = people[name].get("source", "google_contacts")

    return people


def build_people_profiles() -> str:
    people = _load_people()
    PEOPLE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    updated = 0
    upcoming = []

    for name, info in people.items():
        birthday = str(info.get("birthday") or "")
        days = _days_until(birthday) if birthday else None
        if days is not None and days <= 45:
            upcoming.append((days, name, birthday))

        path = PEOPLE_ROOT / f"{name}.md"
        content = f"""# {name}

Type: person
Source: {info.get("source", "")}
Relationship: {info.get("relationship", "")}
Birthday: {birthday}
Phone: {info.get("phone", "")}
Email: {info.get("email", "")}
Address: {info.get("address", "")}
Organization: {info.get("organization", "")}
Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Notes

{info.get("notes", "")}

## Upcoming

"""
        content += f"- Birthday in {days} days\n" if days is not None else "- None\n"
        content += "\n## Related\n\n## History\n\n"

        path.write_text(content, encoding="utf-8")
        updated += 1

    lines = ["# People Report", "", f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "## Upcoming Dates"]

    if upcoming:
        for days, name, birthday in sorted(upcoming):
            lines.append(f"- [[JamesOS/People/{name}|{name}]] birthday in {days} days ({birthday})")
    else:
        lines.append("- None in next 45 days")

    lines.extend(["", "## People"])
    for name in sorted(people):
        lines.append(f"- [[JamesOS/People/{name}|{name}]]")

    (REPORTS / "People.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Updated {updated} people profiles and People report"
