from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from jamesos.config import VAULT


ARCHIVE_ROOT = VAULT / "Archive" / "Email" / "Outlook"
BRAIN_ROOT = VAULT / "JamesOS" / "Brain" / "Email" / "Outlook"
INDEX_PATH = VAULT / "JamesOS" / "Brain" / "Email" / "Index" / "outlook_email_index.jsonl"

KNOWN_PEOPLE = ("Malcolm", "Kevin", "Tom", "Ian", "Luke", "Heather", "James", "Jidapa")
PROJECT_KEYWORDS = {
    "CGI/WGL": (
        "cgi",
        "wgl",
        "washington gas",
        "paving",
        "work request",
        "sfm2",
        "sbx",
        "r2qa",
        "ferc",
        "cpmp",
    ),
    "JamesOS": ("jamesos", "jade"),
    "GCU Teaching": ("gcu", "grand canyon university"),
    "UnityStitches": ("unitystitches", "unity stitches"),
}
WGL_CGI_TERMS = (
    "WGL",
    "CGI",
    "Washington Gas",
    "Paving",
    "Work Request",
    "SFM2",
    "SBX",
    "R2QA",
    "FERC",
    "CPMP",
    "Oracle",
    "PL/SQL",
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
TICKET_RE = re.compile(
    r"\b(?:8\d{4}|(?:INC|REQ|CHG|CASE|BUG|TASK|WGL)[- ]?\d{4,10}|[A-Z][A-Z0-9]{1,9}-\d{2,10})\b",
    re.I,
)
LABELED_TICKET_RE = re.compile(
    r"\b(?:ticket|incident|case|defect)\s*(?:number|no\.?)?\s*[:#-]?\s*(\d{4,10})\b",
    re.I,
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts))
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(value)
        parser.close()
        return parser.text()
    except Exception:
        return re.sub(r"<[^>]+>", " ", value).strip()


def _valid_unicode(value: str) -> str:
    return value.encode("utf-8", errors="replace").decode("utf-8")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", _valid_unicode(str(value or ""))).strip()


def _raw_header_values(message: Any, header: str) -> list[str]:
    """Return headers without invoking headerregistry's strict parsers."""
    try:
        items = message.raw_items()
    except Exception:
        items = getattr(message, "_headers", ())
    try:
        return [
            _valid_unicode(str(value))
            for key, value in items
            if str(key).lower() == header.lower()
        ]
    except Exception:
        return []


def _raw_header_text(message: Any, header: str) -> str:
    values = _raw_header_values(message, header)
    return _clean(values[0]) if values else ""


def _fallback_addresses(values: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        for address in EMAIL_RE.findall(value):
            normalized = address.lower()
            if normalized not in seen:
                seen.add(normalized)
                rows.append({"name": "", "email": normalized})
    if not rows:
        rows.extend(
            {"name": "", "email": "", "raw": value}
            for value in values
            if value.strip()
        )
    return rows


def _addresses(message: Any, header: str) -> list[dict[str, str]]:
    values = _raw_header_values(message, header)
    if not values:
        return []
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        parsed = getaddresses(values)
        for name, address in parsed:
            normalized = address.strip().lower()
            if normalized and not EMAIL_RE.fullmatch(normalized):
                continue
            key = (_clean(name), normalized)
            if not any(key) or key in seen:
                continue
            seen.add(key)
            rows.append({"name": key[0], "email": key[1]})
    except Exception:
        return _fallback_addresses(values)
    return rows or _fallback_addresses(values)


def _decode_part(part: Any) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return _valid_unicode(content.strip())
    except Exception:
        pass
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return _clean(payload)
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except LookupError:
        return payload.decode("utf-8", errors="replace").strip()


def _bodies_and_attachments(message: Any) -> tuple[str, str, list[dict[str, Any]]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []

    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        is_attachment = disposition == "attachment" or bool(filename)
        if is_attachment:
            attachments.append(
                {
                    "filename": _clean(filename),
                    "content_type": content_type,
                    "content_disposition": disposition or "",
                    "content_id": _clean(part.get("Content-ID")),
                    "size_bytes": len(payload) if isinstance(payload, bytes) else 0,
                    "sha256": hashlib.sha256(payload).hexdigest() if isinstance(payload, bytes) else "",
                }
            )
        elif content_type == "text/plain":
            value = _decode_part(part)
            if value:
                text_parts.append(value)
        elif content_type == "text/html":
            value = _decode_part(part)
            if value:
                html_parts.append(value)

    body_text = "\n\n".join(dict.fromkeys(text_parts)).strip()
    body_html = "\n\n".join(dict.fromkeys(html_parts)).strip()
    if not body_text and body_html:
        body_text = _html_to_text(body_html)
    return body_text, body_html, attachments


def _sent_at(message: Any) -> datetime:
    value = _raw_header_text(message, "Date")
    if not value:
        raise ValueError("message has no Date header")
    try:
        sent_at = parsedate_to_datetime(str(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid Date header: {value}") from exc
    if sent_at is None:
        raise ValueError(f"invalid Date header: {value}")
    return sent_at


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I))


def _entities(
    subject: str,
    body_text: str,
    body_html: str,
    address_groups: Iterable[list[dict[str, str]]],
) -> dict[str, list[str]]:
    participants = [row for group in address_groups for row in group]
    participant_text = "\n".join(
        f"{row.get('name', '')} {row.get('email', '')} {row.get('raw', '')}"
        for row in participants
    )
    searchable = "\n".join((subject, participant_text, body_text, _html_to_text(body_html)))

    people = {_clean(row["name"]) for row in participants if _clean(row["name"])}
    people.update(
        name
        for name in KNOWN_PEOPLE
        if _contains_term(searchable, name)
        and not any(_contains_term(person, name) for person in people)
    )

    email_addresses = {
        row.get("email", "").lower()
        for row in participants
        if row.get("email")
    }
    email_addresses.update(match.lower() for match in EMAIL_RE.findall(searchable))

    projects = {
        project
        for project, keywords in PROJECT_KEYWORDS.items()
        if any(_contains_term(searchable, keyword) for keyword in keywords)
    }
    tickets = {match.upper().replace(" ", "-") for match in TICKET_RE.findall(searchable)}
    tickets.update(LABELED_TICKET_RE.findall(searchable))
    terms = {term for term in WGL_CGI_TERMS if _contains_term(searchable, term)}

    return {
        "people": sorted(people, key=str.casefold),
        "email_addresses": sorted(email_addresses),
        "projects": sorted(projects, key=str.casefold),
        "ticket_numbers": sorted(tickets),
        "wgl_cgi_terms": sorted(terms, key=str.casefold),
    }


def _safe_stem(subject: str, sent_at: datetime, digest: str) -> str:
    clean_subject = re.sub(r"[^A-Za-z0-9._ -]+", "", subject).strip()
    clean_subject = re.sub(r"\s+", " ", clean_subject)[:70].strip(" ._") or "no-subject"
    return f"{sent_at.strftime('%H%M%S')}-{clean_subject}-{digest[:12]}"


def _date_dir(root: Path, sent_at: datetime) -> Path:
    return root / sent_at.strftime("%Y") / sent_at.strftime("%m") / sent_at.strftime("%d")


def _address_text(rows: list[dict[str, str]]) -> str:
    values = []
    for row in rows:
        name = row.get("name", "")
        address = row.get("email", "")
        raw = _clean(row.get("raw", ""))
        if name and address:
            values.append(f"{name} <{address}>")
        else:
            values.append(name or address or raw)
    return ", ".join(values)


def _markdown(record: dict[str, Any]) -> str:
    entities = record["entities"]
    searchable_body = record["body_text"] or _html_to_text(record["body_html"])
    lines = [
        f"# {record['subject'] or '(No subject)'}",
        "",
        f"Date Sent: {record['date_sent']}",
        f"From: {_address_text(record['from'])}",
        f"To: {_address_text(record['to'])}",
        f"Cc: {_address_text(record['cc'])}",
        f"Message-ID: {record['message_id']}",
        f"People: {json.dumps(entities['people'], ensure_ascii=False)}",
        f"Email addresses: {json.dumps(entities['email_addresses'], ensure_ascii=False)}",
        f"Projects: {json.dumps(entities['projects'], ensure_ascii=False)}",
        f"Tickets: {json.dumps(entities['ticket_numbers'], ensure_ascii=False)}",
        f"WGL/CGI terms: {json.dumps(entities['wgl_cgi_terms'], ensure_ascii=False)}",
        "",
        "## Message",
        "",
        searchable_body.strip() or "(No textual message body)",
        "",
        "## Attachments",
        "",
    ]
    if record["attachments"]:
        for item in record["attachments"]:
            label = item["filename"] or "(unnamed attachment)"
            lines.append(f"- {label} — {item['content_type']}, {item['size_bytes']} bytes")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def import_eml(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    raw = source.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw)
    sent_at = _sent_at(message)
    subject = _raw_header_text(message, "Subject")
    sender = _addresses(message, "From")
    recipients = _addresses(message, "To")
    cc = _addresses(message, "Cc")
    raw_headers = {
        "from": _raw_header_values(message, "From"),
        "to": _raw_header_values(message, "To"),
        "cc": _raw_header_values(message, "Cc"),
    }
    body_text, body_html, attachments = _bodies_and_attachments(message)
    digest = hashlib.sha256(raw).hexdigest()
    entities = _entities(subject, body_text, body_html, (sender, recipients, cc))

    archive_dir = _date_dir(ARCHIVE_ROOT, sent_at)
    brain_dir = _date_dir(BRAIN_ROOT, sent_at)
    archive_dir.mkdir(parents=True, exist_ok=True)
    brain_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(subject, sent_at, digest)
    raw_path = archive_dir / f"{stem}.eml"
    json_path = archive_dir / f"{stem}.json"
    markdown_path = brain_dir / f"{stem}.md"

    record = {
        "id": digest,
        "source": "Outlook PST export",
        "subject": subject,
        "from": sender,
        "to": recipients,
        "cc": cc,
        "raw_address_headers": raw_headers,
        "date_sent": sent_at.isoformat(),
        "message_id": _raw_header_text(message, "Message-ID"),
        "body_text": body_text,
        "body_html": body_html,
        "attachments": attachments,
        "entities": entities,
        "archive_eml": str(raw_path),
        "archive_json": str(json_path),
        "markdown_path": str(markdown_path),
    }

    if not raw_path.exists():
        shutil.copyfile(source, raw_path)
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(record), encoding="utf-8")
    return record


def _index_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "subject": record["subject"],
        "from": record["from"],
        "to": record["to"],
        "cc": record["cc"],
        "raw_address_headers": record["raw_address_headers"],
        "date_sent": record["date_sent"],
        "message_id": record["message_id"],
        "body_text": record["body_text"],
        "attachments": record["attachments"],
        "entities": record["entities"],
        "markdown_path": record["markdown_path"],
        "archive_json": record["archive_json"],
    }


def _load_index() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not INDEX_PATH.exists():
        return rows
    with INDEX_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("id"):
                rows[row["id"]] = row
    return rows


def _write_index(rows: dict[str, dict[str, Any]]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = INDEX_PATH.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for row in sorted(rows.values(), key=lambda item: (item.get("date_sent", ""), item["id"])):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp_path.replace(INDEX_PATH)


def import_eml_directory(source: str | Path) -> dict[str, Any]:
    root = Path(source).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(root)
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".eml")
    index = _load_index()
    imported = 0
    failures: list[dict[str, str]] = []
    for path in paths:
        try:
            record = import_eml(path)
            index[record["id"]] = _index_row(record)
            imported += 1
        except Exception as exc:
            failures.append({"file": str(path), "error": str(exc)})
    _write_index(index)
    return {
        "status": "ok" if not failures else "partial",
        "found": len(paths),
        "imported": imported,
        "failed": len(failures),
        "failures": failures,
        "index": str(INDEX_PATH),
    }
