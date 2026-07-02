from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT


SEARCH_ROOTS = [
    VAULT / "JamesOS" / "People",
    VAULT / "JamesOS" / "Knowledge",
    VAULT / "JamesOS" / "Knowledge" / "Files",
    VAULT / "JamesOS" / "Reports",
    VAULT / "JamesOS" / "Intake",
    VAULT / "Work",
    VAULT / "Archive" / "Inbox" / "Gmail",
    VAULT / "Archive" / "Inbox" / "GCU",
    VAULT / "Archive" / "Inbox" / "Calendar",
]


def _score(text: str, query: str, path: Path) -> int:
    q = query.lower()
    lower = text.lower()
    score = 0

    if q in path.stem.lower():
        score += 30

    score += lower.count(q) * 5

    if "source: gmail" in lower:
        score += 3
    if "source: google_calendar" in lower:
        score += 3
    if "type: person" in lower:
        score += 5
    if "status: active" in lower:
        score += 2

    return score


def build_rich_context(query: str, limit: int = 12, chars_per_file: int = 1800) -> str:
    matches = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            score = _score(text, query, path)
            if score > 0:
                matches.append((score, path.stat().st_mtime, path, text))

    matches.sort(reverse=True, key=lambda x: (x[0], x[1]))

    lines = [
        "# Rich Context",
        "",
        f"Query: {query}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    if not matches:
        lines.append("No rich context matches found.")
        return "\n".join(lines)

    for score, _mtime, path, text in matches[:limit]:
        rel = path.relative_to(VAULT).with_suffix("").as_posix()
        lines.extend([
            f"## [[{rel}]]",
            f"Score: {score}",
            "",
            text[:chars_per_file],
            "",
            "---",
            "",
        ])

    return "\n".join(lines)
