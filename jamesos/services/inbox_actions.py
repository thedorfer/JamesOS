import shutil
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.inbox_review import review_inbox
from jamesos.services.refresh import refresh_dashboards


def archive_inbox_item(filename: str) -> str:
    inbox_dir = VAULT / "00-Inbox"
    archive_dir = VAULT / "Archive" / "Inbox"
    archive_dir.mkdir(parents=True, exist_ok=True)

    name = filename.strip()
    if not name.endswith(".md"):
        name += ".md"

    source = inbox_dir / name

    if not source.exists():
        matches = list(inbox_dir.glob(f"*{filename.strip()}*.md"))
        if len(matches) == 1:
            source = matches[0]
        elif len(matches) > 1:
            return "Multiple inbox matches found:\n" + "\n".join(str(m.relative_to(VAULT)) for m in matches)
        else:
            return f"Inbox item not found: {filename}"

    target = archive_dir / source.name

    counter = 2
    while target.exists():
        target = archive_dir / f"{source.stem} ({counter}){source.suffix}"
        counter += 1

    shutil.move(str(source), str(target))

    review_inbox()
    refresh_dashboards()

    return f"Archived {source.relative_to(VAULT)} to {target.relative_to(VAULT)}"
