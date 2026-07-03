import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job

ATTACHMENTS = VAULT / "00-Inbox" / "Attachments"
ARCHIVE = VAULT / "Archive" / "Attachments"

TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".sql", ".py"}


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _queue_attachment(path: Path) -> None:
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


def _archive_path(filename: str) -> Path:
    now = datetime.now()
    target_root = ARCHIVE / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    target_root.mkdir(parents=True, exist_ok=True)
    return _unique_path(target_root / filename)


def _ingest_saved_file(path: Path) -> dict:
    _queue_attachment(path)
    target = _archive_path(path.name)
    shutil.move(str(path), str(target))
    return {"filename": target.name, "path": str(target), "status": "archived"}


def ingest_attachment_uploads(files: Iterable[UploadFile]) -> dict:
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    results = []

    for upload in files:
        filename = Path(upload.filename or "uploaded_file").name
        inbox_path = _unique_path(ATTACHMENTS / filename)

        with inbox_path.open("wb") as out:
            shutil.copyfileobj(upload.file, out)

        results.append(_ingest_saved_file(inbox_path))

    return {"status": "ok", "imported": len(results), "files": results}


def ingest_attachments(files: Iterable[UploadFile] | None = None):
    if files is not None:
        return ingest_attachment_uploads(files)

    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    imported = []

    for path in sorted(ATTACHMENTS.iterdir()):
        if not path.is_file():
            continue
        imported.append(_ingest_saved_file(path))

    return f"Attachment ingest complete. Imported: {len(imported)}."
