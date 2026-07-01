from datetime import datetime
import re

from jamesos.config import VAULT


def _safe_title(title: str) -> str:
    title = title.strip() or "Untitled Capture"
    title = re.sub(r'[\\/:*?"<>|]+', "-", title)
    title = re.sub(r"\s+", " ", title)
    return title[:80]


def capture_inbox(title: str, content: str, source: str = "manual") -> str:
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    inbox_dir = VAULT / "00-Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_title(title)
    path = inbox_dir / f"{date} - {safe_title}.md"

    counter = 2
    while path.exists():
        path = inbox_dir / f"{date} - {safe_title} ({counter}).md"
        counter += 1

    text = f"""# {safe_title}

Source: {source}
Captured: {timestamp}
Status: inbox

## Raw Capture

{content.strip()}

## Cleanup Notes

## Suggested Destination

"""

    path.write_text(text, encoding="utf-8")
    return f"Captured inbox note: {path.relative_to(VAULT)}"
