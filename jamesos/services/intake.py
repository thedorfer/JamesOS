from datetime import datetime
import re
from pathlib import Path

from jamesos.config import VAULT
from jamesos.tools.inbox import capture_inbox
from jamesos.services.inbox_cleanup import suggest_inbox_cleanup
from jamesos.services.refresh import refresh_dashboards


INTAKE_ROOT = VAULT / "JamesOS" / "Intake"


def _safe_name(value: str) -> str:
    value = value.strip() or "Untitled Intake"
    value = re.sub(r'[\\/:*?"<>|]+', "-", value)
    value = re.sub(r"\s+", " ", value)
    return value[:80]


def intake_item(
    title: str,
    content: str,
    source: str = "manual",
    source_detail: str = "",
) -> str:
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    date = now.strftime("%Y-%m-%d")

    INTAKE_ROOT.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_name(title)
    raw_path = INTAKE_ROOT / f"{date} - {safe_title}.md"

    counter = 2
    while raw_path.exists():
        raw_path = INTAKE_ROOT / f"{date} - {safe_title} ({counter}).md"
        counter += 1

    raw_text = f"""# {safe_title}

Source: {source}
Source Detail: {source_detail}
Received: {timestamp}
Status: captured

## Content

{content.strip()}

"""

    raw_path.write_text(raw_text, encoding="utf-8")

    capture_result = capture_inbox(
        title=safe_title,
        content=f"""Source: {source}
Source Detail: {source_detail}
Received: {timestamp}

{content.strip()}""",
        source=source,
    )

    cleanup_result = suggest_inbox_cleanup()
    refresh_dashboards()

    return "\n".join([
        f"Created intake item: {raw_path.relative_to(VAULT)}",
        capture_result,
        cleanup_result,
    ])
