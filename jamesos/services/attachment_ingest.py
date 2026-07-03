import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from jamesos.config import VAULT
from jamesos.core.queue import enqueue_job

ATTACHMENTS = VAULT / "00-Inbox" / "Attachments"
ARCHIVE = VAULT / "Archive" / "Attachments"
PROCESSING_REPORTS = VAULT / "JamesOS" / "Reports" / "Uploads"

TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".sql", ".py"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
PDF_EXTS = {".pdf"}
DOC_EXTS = {".doc", ".docx", ".rtf", ".odt"}
SHEET_EXTS = {".xls", ".xlsx", ".csv", ".ods"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOC_EXTS:
        return "document"
    if ext in SHEET_EXTS:
        return "spreadsheet"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in TEXT_EXTS:
        return "text"
    return "file"


def _queue_attachment(path: Path, kind: str) -> str:
    title = f"Attachment - {path.name}"

    if path.suffix.lower() in TEXT_EXTS:
        content = path.read_text(encoding="utf-8", errors="ignore")
    else:
        content = (
            f"Attachment captured for review: {path.name}\n"
            f"Kind: {kind}\n"
            f"Path: {path}\n"
            "Status: Stored and queued for deeper processing."
        )

    return enqueue_job("intake", {
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


def _processing_plan(kind: str) -> list[str]:
    plans = {
        "image": ["store original", "extract EXIF/date/GPS when present", "queue image understanding", "add to timeline", "prepare searchable memory"],
        "pdf": ["store original", "extract text", "summarize", "extract people/projects/topics", "prepare searchable memory"],
        "document": ["store original", "extract text", "summarize", "extract people/projects/topics", "prepare searchable memory"],
        "spreadsheet": ["store original", "profile sheets/columns", "extract useful tables", "prepare searchable memory"],
        "audio": ["store original", "queue transcription", "summarize", "prepare searchable memory"],
        "video": ["store original", "queue transcript/keyframes", "summarize", "prepare searchable memory"],
        "text": ["store original", "index text", "extract people/projects/topics", "prepare searchable memory"],
    }
    return plans.get(kind, ["store original", "classify file", "prepare searchable memory"])


def _write_processing_report(result: dict) -> str:
    PROCESSING_REPORTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = PROCESSING_REPORTS / "Latest Upload.md"
    steps = "\n".join(f"- {step}" for step in result.get("processing_plan", []))
    path.write_text(
        "\n".join([
            "# Latest Upload",
            "",
            f"Updated: {now}",
            f"File: {result.get('filename')}",
            f"Kind: {result.get('kind')}",
            f"Path: {result.get('path')}",
            f"Processing job: {result.get('processing_job')}",
            "",
            "## Processing Plan",
            "",
            steps or "- Stored for review.",
        ]),
        encoding="utf-8",
    )
    return str(path)


def _queue_processing(path: Path, kind: str) -> str:
    return enqueue_job("attachment_process", {
        "path": str(path),
        "filename": path.name,
        "kind": kind,
        "processing_plan": _processing_plan(kind),
    })


def _ingest_saved_file(path: Path) -> dict:
    kind = _file_kind(path)
    target = _archive_path(path.name)
    shutil.move(str(path), str(target))

    intake_job = _queue_attachment(target, kind)
    processing_job = _queue_processing(target, kind)

    result = {
        "filename": target.name,
        "path": str(target),
        "kind": kind,
        "status": "stored_and_queued",
        "intake_job": intake_job,
        "processing_job": processing_job,
        "processing_plan": _processing_plan(kind),
    }
    result["report"] = _write_processing_report(result)
    return result


def ingest_attachment_uploads(files: Iterable[UploadFile]) -> dict:
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    results = []

    for upload in files:
        filename = Path(upload.filename or "uploaded_file").name
        inbox_path = _unique_path(ATTACHMENTS / filename)

        with inbox_path.open("wb") as out:
            shutil.copyfileobj(upload.file, out)

        results.append(_ingest_saved_file(inbox_path))

    return {
        "status": "ok",
        "imported": len(results),
        "files": results,
        "message": _summary_message(results),
    }


def _summary_message(results: list[dict]) -> str:
    if not results:
        return "No files were uploaded."
    if len(results) == 1:
        item = results[0]
        kind = item.get("kind", "file")
        return f"I stored {item.get('filename')} as a {kind} and queued it for processing."
    return f"I stored {len(results)} files and queued them for processing."


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
