import hashlib
import json
import mimetypes
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
INGEST_ROOT = VAULT / "JamesOS" / "Brain" / "Ingest"
TIMELINE_ROOT = VAULT / "JamesOS" / "Timeline"

TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".sql", ".py"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
PDF_EXTS = {".pdf"}
DOC_EXTS = {".doc", ".docx", ".rtf", ".odt"}
SHEET_EXTS = {".xls", ".xlsx", ".csv", ".ods"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _now() -> datetime:
    return datetime.now()


def _date_parts(dt: datetime) -> tuple[str, str, str]:
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")


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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _archive_path(filename: str, dt: datetime) -> Path:
    year, month, day = _date_parts(dt)
    target_root = ARCHIVE / year / month / day
    target_root.mkdir(parents=True, exist_ok=True)
    return _unique_path(target_root / filename)


def _ingest_paths(dt: datetime, filename: str) -> dict[str, Path]:
    year, month, day = _date_parts(dt)
    root = INGEST_ROOT / year / month / day / Path(filename).stem
    raw = root / "raw"
    derived = root / "derived"
    raw.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    return {"root": root, "raw": raw, "derived": derived}


def _extract_basic(path: Path, kind: str) -> dict:
    stat = path.stat()
    extracted: dict = {
        "filename": path.name,
        "extension": path.suffix.lower(),
        "kind": kind,
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "size_bytes": stat.st_size,
        "sha256": _sha256(path),
        "stored_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "text_preview": "",
        "image": {},
        "needs": [],
    }

    if path.suffix.lower() in TEXT_EXTS:
        text = path.read_text(encoding="utf-8", errors="ignore")
        extracted["text_preview"] = text[:4000]
        extracted["needs"].append("entity extraction")
    elif kind == "image":
        extracted["needs"].extend(["image captioning", "OCR", "EXIF review", "timeline placement"])
        try:
            from PIL import Image
            with Image.open(path) as img:
                extracted["image"] = {
                    "format": img.format,
                    "width": img.width,
                    "height": img.height,
                    "mode": img.mode,
                    "has_exif": bool(getattr(img, "getexif", lambda: {})()),
                }
        except Exception as exc:
            extracted["image"] = {"note": f"basic image metadata unavailable: {exc}"}
    elif kind == "pdf":
        extracted["needs"].extend(["PDF text extraction", "OCR if scanned", "summary", "entity extraction"])
    elif kind == "document":
        extracted["needs"].extend(["document text extraction", "summary", "entity extraction"])
    elif kind == "spreadsheet":
        extracted["needs"].extend(["sheet profiling", "table extraction", "summary"])
    elif kind == "audio":
        extracted["needs"].extend(["speech-to-text", "summary", "entity extraction"])
    elif kind == "video":
        extracted["needs"].extend(["transcript", "keyframes", "summary", "entity extraction"])
    else:
        extracted["needs"].append("classification")

    return extracted


def _processing_plan(kind: str) -> list[str]:
    plans = {
        "image": ["archive original", "extract metadata", "OCR visible text", "describe scene", "detect important people/places/topics", "add to timeline", "make searchable"],
        "pdf": ["archive original", "extract text", "OCR if needed", "summarize", "extract people/projects/topics", "make searchable"],
        "document": ["archive original", "extract text", "summarize", "extract people/projects/topics", "make searchable"],
        "spreadsheet": ["archive original", "profile sheets/columns", "extract useful tables", "summarize", "make searchable"],
        "audio": ["archive original", "transcribe", "summarize", "extract people/projects/topics", "make searchable"],
        "video": ["archive original", "extract transcript/keyframes", "summarize", "make searchable"],
        "text": ["archive original", "index text", "extract people/projects/topics", "make searchable"],
    }
    return plans.get(kind, ["archive original", "classify file", "make searchable"])


def _understanding_stub(path: Path, kind: str, extracted: dict) -> dict:
    # This is the first pass. The background jobs can replace/enrich this with OCR,
    # local vision, embeddings, and graph links as those processors are added.
    summary = f"Received {path.name} as a {kind}. Original stored and queued for deeper understanding."
    if kind == "image":
        image = extracted.get("image") or {}
        if image.get("width") and image.get("height"):
            summary = f"Received image {path.name} ({image['width']}x{image['height']}). Queued for captioning, OCR, timeline, and searchable memory."
    elif extracted.get("text_preview"):
        summary = f"Received text file {path.name}. Text was captured and queued for entity extraction and search."

    return {
        "summary": summary,
        "confidence": "initial",
        "topics": [kind, "upload", "inbox"],
        "people": [],
        "projects": [],
        "actions": extracted.get("needs", []),
    }


def _write_manifest(paths: dict[str, Path], archived_path: Path, kind: str, extracted: dict, understanding: dict, jobs: dict) -> dict:
    manifest = {
        "status": "received_archived_classified_extracted_queued",
        "received_at": _now().isoformat(timespec="seconds"),
        "filename": archived_path.name,
        "kind": kind,
        "archive_path": str(archived_path),
        "extracted": extracted,
        "understanding": understanding,
        "processing_plan": _processing_plan(kind),
        "jobs": jobs,
    }
    manifest_path = paths["derived"] / "manifest.json"
    summary_path = paths["derived"] / "summary.md"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary_path.write_text(_manifest_markdown(manifest), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    manifest["summary_path"] = str(summary_path)
    return manifest


def _manifest_markdown(manifest: dict) -> str:
    plan = "\n".join(f"- {step}" for step in manifest.get("processing_plan", []))
    needs = "\n".join(f"- {item}" for item in manifest.get("extracted", {}).get("needs", [])) or "- None"
    return "\n".join([
        f"# Upload: {manifest.get('filename')}",
        "",
        f"Status: {manifest.get('status')}",
        f"Kind: {manifest.get('kind')}",
        f"Archive: {manifest.get('archive_path')}",
        "",
        "## Initial Understanding",
        "",
        manifest.get("understanding", {}).get("summary", "Stored for processing."),
        "",
        "## Processing Plan",
        "",
        plan,
        "",
        "## Needs",
        "",
        needs,
    ])


def _write_latest_report(manifest: dict) -> str:
    PROCESSING_REPORTS.mkdir(parents=True, exist_ok=True)
    path = PROCESSING_REPORTS / "Latest Upload.md"
    path.write_text(_manifest_markdown(manifest), encoding="utf-8")
    return str(path)


def _write_timeline_entry(manifest: dict) -> str:
    today = _now().strftime("%Y-%m-%d")
    TIMELINE_ROOT.mkdir(parents=True, exist_ok=True)
    path = TIMELINE_ROOT / f"{today}.md"
    block = "\n".join([
        "",
        f"## Upload - {manifest.get('filename')}",
        f"- Kind: {manifest.get('kind')}",
        f"- Summary: {manifest.get('understanding', {}).get('summary')}",
        f"- Archive: {manifest.get('archive_path')}",
        f"- Manifest: {manifest.get('manifest_path')}",
    ])
    with path.open("a", encoding="utf-8") as f:
        f.write(block + "\n")
    return str(path)


def _queue_jobs(archived_path: Path, kind: str, extracted: dict) -> dict:
    title = f"Attachment - {archived_path.name}"
    if extracted.get("text_preview"):
        content = extracted["text_preview"]
    else:
        content = f"Attachment captured for review: {archived_path.name}\nKind: {kind}\nPath: {archived_path}\nStatus: Stored and queued for deeper processing."

    intake_job = enqueue_job("intake", {
        "title": title,
        "content": content,
        "source": "attachment",
        "source_detail": str(archived_path),
    })
    process_job = enqueue_job("attachment_process", {
        "path": str(archived_path),
        "filename": archived_path.name,
        "kind": kind,
        "processing_plan": _processing_plan(kind),
        "needs": extracted.get("needs", []),
    })
    return {"intake": intake_job, "attachment_process": process_job}


def _ingest_saved_file(path: Path) -> dict:
    received_at = _now()
    kind = _file_kind(path)
    paths = _ingest_paths(received_at, path.name)

    archived_path = _archive_path(path.name, received_at)
    shutil.move(str(path), str(archived_path))

    raw_copy = _unique_path(paths["raw"] / archived_path.name)
    shutil.copy2(archived_path, raw_copy)

    extracted = _extract_basic(archived_path, kind)
    understanding = _understanding_stub(archived_path, kind, extracted)
    jobs = _queue_jobs(archived_path, kind, extracted)
    manifest = _write_manifest(paths, archived_path, kind, extracted, understanding, jobs)
    manifest["report"] = _write_latest_report(manifest)
    manifest["timeline"] = _write_timeline_entry(manifest)

    return {
        "filename": archived_path.name,
        "path": str(archived_path),
        "kind": kind,
        "status": manifest["status"],
        "summary": understanding["summary"],
        "manifest": manifest.get("manifest_path"),
        "report": manifest.get("report"),
        "timeline": manifest.get("timeline"),
        "processing_plan": manifest.get("processing_plan", []),
        "jobs": jobs,
    }


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
        return "\n".join([
            f"I received `{item.get('filename')}` as a {kind}.",
            "",
            "I archived the original, created an ingest manifest, added it to today's timeline, and queued it for deeper understanding.",
            "",
            "Next processors will handle OCR, captions, summaries, entities, embeddings, and graph links as available.",
        ])
    return f"I stored {len(results)} files, created ingest manifests, added them to today's timeline, and queued them for processing."


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
