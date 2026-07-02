from datetime import datetime, date
from pathlib import Path

from jamesos.config import VAULT
from jamesos.config.loader import get_config

PEOPLE_ROOT = VAULT / "JamesOS" / "People"
REPORTS = VAULT / "JamesOS" / "Reports"


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


def build_people_profiles() -> str:
    cfg = get_config("contacts.yaml").get("contacts", {})
    people = cfg.get("people", {})

    PEOPLE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    updated = 0
    upcoming = []

    for name, info in people.items():
        path = PEOPLE_ROOT / f"{name}.md"

        birthday = info.get("birthday") or ""
        days = _days_until(str(birthday)) if birthday else None

        if days is not None and days <= 45:
            upcoming.append((days, name, birthday))

        content = f"""# {name}

Type: person
Relationship: {info.get("relationship", "")}
Birthday: {birthday}
Phone: {info.get("phone", "")}
Email: {info.get("email", "")}
Address: {info.get("address", "")}
Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## Notes

{info.get("notes", "")}

## Upcoming

"""

        if days is not None:
            content += f"- Birthday in {days} days\n"
        else:
            content += "- None\n"

        content += """

## Related

## History

"""

        path.write_text(content, encoding="utf-8")
        updated += 1

    lines = [
        "# People Report",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Upcoming Dates",
    ]

    if upcoming:
        for days, name, birthday in sorted(upcoming):
            lines.append(f"- [[JamesOS/People/{name}|{name}]] birthday in {days} days ({birthday})")
    else:
        lines.append("- None in next 45 days")

    lines.extend(["", "## People"])
    for name in sorted(people):
        lines.append(f"- [[JamesOS/People/{name}|{name}]]")

    report = REPORTS / "People.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return f"Updated {updated} people profiles and People report"
