from __future__ import annotations

import json
from io import BytesIO
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any

from jamesos.config import JAMESOS_DATA
from jamesos.services.application_shell import CONVERSATION_RE
from jamesos.services.product_orchestrator import _atomic_json


ROOT = JAMESOS_DATA / "JamesOS" / "ApplicationShell" / "attachments"
MAX_BYTES = int(os.environ.get("JAMESOS_SHELL_UPLOAD_MAX_BYTES", 10 * 1024 * 1024))
ORPHAN_TTL_SECONDS = int(os.environ.get("JAMESOS_SHELL_UPLOAD_ORPHAN_TTL_SECONDS", 24 * 60 * 60))
MAX_EXTRACT_CHARS = int(os.environ.get("JAMESOS_SHELL_ATTACHMENT_EXTRACT_CHARS", 20_000))
MAX_TOTAL_CONTEXT_CHARS = int(os.environ.get("JAMESOS_SHELL_ATTACHMENT_CONTEXT_CHARS", 40_000))
REFERENCE_ROOTS = (JAMESOS_DATA / "JamesOS" / "ApplicationShell" / "conversations", JAMESOS_DATA / "JamesOS" / "Jobs")
ALLOWED = {
    "text/plain": {".txt"}, "text/markdown": {".md", ".markdown"},
    "application/json": {".json"}, "text/csv": {".csv"},
    "application/pdf": {".pdf"}, "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"}, "image/webp": {".webp"},
}


def sanitize_filename(value: str) -> str:
    name = str(value or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]
    return name or "attachment"


def _detected_type(data: bytes) -> str | None:
    if data.startswith((b"\x7fELF",b"MZ",b"PK\x03\x04",b"\x1f\x8b")): return None
    if data.startswith(b"%PDF-"): return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if data.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP": return "image/webp"
    if b"\x00" in data[:8192]: return None
    try: text=data.decode("utf-8")
    except UnicodeDecodeError: return None
    if text.startswith("#!") or re.search(r"(?is)<\s*(?:script|html|iframe)\b|\b(?:eval|exec)\s*\(",text): return None
    return "text"


def store_attachment(*, conversation_id: str, filename: str, content_type: str, data: bytes) -> dict[str, Any]:
    if not CONVERSATION_RE.fullmatch(conversation_id): raise ValueError("Invalid conversation ID.")
    if not data: raise ValueError("The selected file is empty.")
    if len(data) > MAX_BYTES: raise ValueError("The selected file exceeds the upload size limit.")
    clean = sanitize_filename(filename); suffix = Path(clean).suffix.casefold()
    if content_type not in ALLOWED or suffix not in ALLOWED[content_type]: raise ValueError("This file type is not supported.")
    detected = _detected_type(data)
    text_types={"text/plain","text/markdown","application/json","text/csv"}
    if detected is None or (detected=="text" and content_type not in text_types) or (detected!="text" and detected!=content_type): raise ValueError("The file content does not match its declared type.")
    if detected == "text" and content_type == "application/json":
        try: json.loads(data)
        except Exception as exc: raise ValueError("The JSON attachment is not valid JSON.") from exc
    attachment_id = secrets.token_urlsafe(24); directory = ROOT / conversation_id
    directory.mkdir(parents=True, exist_ok=True); (directory / attachment_id).write_bytes(data)
    meta = {"attachment_id": attachment_id, "filename": clean, "content_type": content_type, "size": len(data), "conversation_id": conversation_id, "created_at": time.time()}
    _atomic_json(directory / f"{attachment_id}.json", meta)
    return {key: meta[key] for key in ("attachment_id", "filename", "content_type", "size")}


def verify_attachments(conversation_id: str, values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or len(values) > 10: raise ValueError("Attachments must be a bounded list.")
    verified = []
    for value in values:
        if not isinstance(value, dict) or set(value) - {"attachment_id", "filename", "content_type", "size"}: raise ValueError("Invalid attachment metadata.")
        attachment_id = str(value.get("attachment_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", attachment_id): raise ValueError("Invalid attachment ID.")
        path = ROOT / conversation_id / f"{attachment_id}.json"
        if not path.is_file(): raise ValueError("Attachment does not belong to this conversation.")
        meta = json.loads(path.read_text(encoding="utf-8"))
        if meta.get("conversation_id") != conversation_id or not (ROOT / conversation_id / attachment_id).is_file(): raise ValueError("Attachment is unavailable.")
        for key in ("filename","content_type","size"):
            if key in value and value[key] != meta.get(key): raise ValueError("Attachment metadata does not match the stored upload.")
        verified.append({key: meta[key] for key in ("attachment_id", "filename", "content_type", "size")})
    return verified


def process_chat_attachments(conversation_id: str, values: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],list[dict[str,str]]]:
    receipts=[];contexts=[];remaining=MAX_TOTAL_CONTEXT_CHARS
    for meta in values:
        attachment_id=meta["attachment_id"];data=(ROOT/conversation_id/attachment_id).read_bytes();content_type=meta["content_type"]
        receipt={"attachment_id":attachment_id,"filename":meta["filename"],"content_type":content_type,"byte_count":len(data),"ingestion_state":"processed","processing_method":"validated_binary","extracted_character_count":0}
        extracted=""
        if content_type in {"text/plain","text/markdown","application/json","text/csv"}:
            extracted=data.decode("utf-8")[:MAX_EXTRACT_CHARS];receipt["processing_method"]="utf8_text_extraction";receipt["extracted_character_count"]=len(extracted)
        elif content_type=="application/pdf":
            try:
                from pypdf import PdfReader
                reader=PdfReader(BytesIO(data));receipt["page_count"]=len(reader.pages);parts=[]
                for page in reader.pages:
                    if sum(map(len,parts))>=MAX_EXTRACT_CHARS:break
                    parts.append(page.extract_text() or "")
                extracted="\n".join(parts)[:MAX_EXTRACT_CHARS];receipt["processing_method"]="pdf_text_extraction";receipt["extracted_character_count"]=len(extracted)
            except Exception:receipt["processing_method"]="pdf_validation_no_text"
        else:
            from PIL import Image
            with Image.open(BytesIO(data)) as image:
                image.load();receipt["dimensions"]={"width":int(image.width),"height":int(image.height)}
            receipt["processing_method"]="image_decode";receipt["image_pipeline_available"]=True;receipt["visual_understanding_performed"]=False
        if extracted and remaining>0:
            bounded=extracted[:remaining];contexts.append({"attachment_id":attachment_id,"filename":meta["filename"],"untrusted_text":bounded});remaining-=len(bounded)
        receipts.append(receipt)
    return receipts,contexts


def _is_referenced(attachment_id: str, roots: tuple[Path, ...] = REFERENCE_ROOTS) -> bool:
    needle = attachment_id.encode()
    for root in roots:
        if not root.is_dir(): continue
        for path in root.rglob("*.json"):
            try:
                if needle in path.read_bytes(): return True
            except OSError: continue
    return False


def delete_pending_attachment(conversation_id: str, attachment_id: str, *, roots: tuple[Path, ...] = REFERENCE_ROOTS) -> bool:
    verified = verify_attachments(conversation_id, [{"attachment_id": attachment_id}])
    if not verified or _is_referenced(attachment_id, roots): return False
    directory = ROOT / conversation_id
    (directory / attachment_id).unlink(missing_ok=True);(directory / f"{attachment_id}.json").unlink(missing_ok=True)
    try: directory.rmdir()
    except OSError: pass
    return True


def cleanup_expired_orphans(*, now: float | None = None, ttl_seconds: int = ORPHAN_TTL_SECONDS, roots: tuple[Path, ...] = REFERENCE_ROOTS) -> dict[str, int]:
    now=time.time() if now is None else now;removed=preserved=0
    if not ROOT.is_dir(): return {"removed":0,"preserved":0}
    for metadata_path in ROOT.glob("*/*.json"):
        try:meta=json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception: continue
        attachment_id=str(meta.get("attachment_id") or "");conversation_id=str(meta.get("conversation_id") or "")
        if now-float(meta.get("created_at") or metadata_path.stat().st_mtime)<ttl_seconds: continue
        if _is_referenced(attachment_id,roots):preserved+=1;continue
        try:
            delete_pending_attachment(conversation_id,attachment_id,roots=roots);removed+=1
        except ValueError: continue
    return {"removed":removed,"preserved":preserved}
