import json
from datetime import datetime, timedelta, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jamesos.config import VAULT
from jamesos.config.loader import get_config
from jamesos.core.queue import enqueue_job

SCOPES = ["https://www.googleapis.com/auth/calendar"]

SECRETS = VAULT / "JamesOS" / "Secrets"
DATABASE = VAULT / "JamesOS" / "Database" / "calendar"
CREDENTIALS_FILE = SECRETS / "gmail_credentials.json"
TOKEN_FILE = SECRETS / "calendar_token.json"
PROCESSED_FILE = DATABASE / "processed.json"


def _load_processed() -> dict:
    DATABASE.mkdir(parents=True, exist_ok=True)
    if not PROCESSED_FILE.exists():
        return {"events": {}}
    return json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))


def _save_processed(data: dict) -> None:
    DATABASE.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _calendar_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"Missing OAuth credentials: {CREDENTIALS_FILE}")

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def _event_time(value: dict) -> str:
    return value.get("dateTime") or value.get("date") or ""


def import_google_calendar() -> str:
    cfg = get_config("calendar.yaml").get("calendar", {})

    calendars = cfg.get("calendars", ["primary"])
    days_back = int(cfg.get("days_back", 30))
    days_forward = int(cfg.get("days_forward", 365))
    max_results = int(cfg.get("max_results", 50))
    import_description = bool(cfg.get("import_description", True))
    import_attendees = bool(cfg.get("import_attendees", True))

    service = _calendar_service()
    processed = _load_processed()

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).isoformat()
    time_max = (now + timedelta(days=days_forward)).isoformat()

    imported = 0
    skipped = 0

    for calendar_id in calendars:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])

        for event in events:
            event_id = event.get("id")
            updated = event.get("updated", "")
            key = f"{calendar_id}:{event_id}"

            existing = processed.get("events", {}).get(key)
            if existing and existing.get("updated") == updated:
                skipped += 1
                continue

            title = event.get("summary", "(No Title)")
            start = _event_time(event.get("start", {}))
            end = _event_time(event.get("end", {}))
            location = event.get("location", "")
            organizer = event.get("organizer", {}).get("email", "")
            html_link = event.get("htmlLink", "")

            content = [
                f"Calendar: {calendar_id}",
                f"Event ID: {event_id}",
                f"Updated: {updated}",
                f"Title: {title}",
                f"Start: {start}",
                f"End: {end}",
                f"Location: {location}",
                f"Organizer: {organizer}",
                f"Google Calendar Link: {html_link}",
                "",
            ]

            if import_attendees:
                content.append("## Attendees")
                for attendee in event.get("attendees", []):
                    email = attendee.get("email", "")
                    status = attendee.get("responseStatus", "")
                    content.append(f"- {email} ({status})")
                content.append("")

            if import_description:
                content.extend([
                    "## Description",
                    event.get("description", "") or "",
                    "",
                ])

            enqueue_job("intake", {
                "title": f"Calendar - {title}",
                "content": "\n".join(content),
                "source": "google_calendar",
                "source_detail": f"calendar:{calendar_id}; event:{event_id}",
                "calendar": {
                    "calendar_id": calendar_id,
                    "event_id": event_id,
                    "updated": updated,
                },
            })

            processed.setdefault("events", {})[key] = {
                "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "calendar_id": calendar_id,
                "event_id": event_id,
                "title": title,
                "start": start,
                "end": end,
                "updated": updated,
                "status": "queued",
            }

            imported += 1

    _save_processed(processed)

    return f"Google Calendar import complete. Imported: {imported}. Skipped unchanged: {skipped}."
