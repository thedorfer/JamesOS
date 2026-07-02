import shutil
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job

ATTACHMENTS = VAULT / "00-Inbox" / "Attachments"
ARCHIVE = VAULT / "Archive" / "Attachments"


TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".sql", ".py"}


def ingest_attachments() -> str:
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    year = datetime.now().strftime("%Y")
    target_root = ARCHIVE / year
    target_root.mkdir(parents=True, exist_ok=True)

    imported = 0

    for path in sorted(ATTACHMENTS.iterdir()):
        if not path.is_file():
            continue

        title = f"Attachment - {path.name}"
        ext = path.suffix.lower()

        if ext in TEXT_EXTS:
            content = path.read_text(encoding="utf-8", errors="ignore")
        else:
            content = f"Attachment captured for review: {path.name}\nPath: {path}"

        enqueue_job("intake", {
            "title": title,
            "content": content,
            "source": "attachment",
            "source_detail": str(path),
        })

        target = target_root / path.name
        counter = 2
        while target.exists():
            target = target_root / f"{path.stem} ({counter}){path.suffix}"
            counter += 1

        shutil.move(str(path), str(target))
        imported += 1

    return f"Attachment ingest complete. Imported: {imported}."
