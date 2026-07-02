import base64
import json
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jamesos.config import VAULT
from jamesos.config.loader import get_config
from jamesos.core.queue import enqueue_job

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

SECRETS = VAULT / "JamesOS" / "Secrets"
DATABASE = VAULT / "JamesOS" / "Database" / "gmail"
CREDENTIALS_FILE = SECRETS / "gmail_credentials.json"
TOKEN_FILE = SECRETS / "gmail_token.json"
PROCESSED_FILE = DATABASE / "processed.json"


def _load_processed() -> dict:
    DATABASE.mkdir(parents=True, exist_ok=True)
    if not PROCESSED_FILE.exists():
        return {"threads": {}}
    return json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))


def _save_processed(data: dict) -> None:
    DATABASE.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _gmail_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"Missing Gmail credentials: {CREDENTIALS_FILE}")

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def _header(message: dict, name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(data: str) -> str:
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")


def _extract_text(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime == "text/plain":
        return _decode_body(body.get("data", ""))

    parts = payload.get("parts", [])
    texts = []

    for part in parts:
        texts.append(_extract_text(part))

    return "\n".join(t for t in texts if t.strip())


def import_gmail_label() -> str:
    cfg = get_config("gmail.yaml").get("gmail", {})
    label_name = cfg.get("label", "JamesOS")
    max_results = int(cfg.get("max_results", 10))

    service = _gmail_service()
    processed = _load_processed()

    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    label = next((l for l in labels if l.get("name") == label_name), None)

    if not label:
        return f"Gmail label not found: {label_name}"

    response = service.users().messages().list(
        userId="me",
        labelIds=[label["id"]],
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", [])
    imported = 0
    skipped = 0

    for item in messages:
        msg = service.users().messages().get(
            userId="me",
            id=item["id"],
            format="full",
        ).execute()

        thread_id = msg.get("threadId")

        if thread_id in processed.get("threads", {}):
            skipped += 1
            continue

        thread = service.users().threads().get(
            userId="me",
            id=thread_id,
            format="full",
        ).execute()

        thread_messages = thread.get("messages", [])
        first = thread_messages[0] if thread_messages else msg

        subject = _header(first, "Subject") or "(No Subject)"
        sender = _header(first, "From")
        date = _header(first, "Date")

        content_parts = [
            f"From: {sender}",
            f"Subject: {subject}",
            f"Date: {date}",
            f"Gmail Thread ID: {thread_id}",
            "",
            "## Thread Messages",
            "",
        ]

        for message in thread_messages:
            content_parts.extend([
                "---",
                f"From: {_header(message, 'From')}",
                f"To: {_header(message, 'To')}",
                f"Date: {_header(message, 'Date')}",
                "",
                _extract_text(message.get("payload", {})).strip(),
                "",
            ])

        enqueue_job("intake", {
            "title": subject,
            "content": "\n".join(content_parts),
            "source": "gmail",
            "source_detail": f"label:{label_name}; thread:{thread_id}",
        })

        processed["threads"][thread_id] = {
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "subject": subject,
            "label": label_name,
        }

        imported += 1

    _save_processed(processed)

    return f"Gmail import complete. Imported: {imported}. Skipped duplicates: {skipped}."
