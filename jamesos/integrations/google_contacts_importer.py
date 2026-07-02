import json
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from jamesos.config import VAULT
from jamesos.config.loader import get_config

SCOPES = ["https://www.googleapis.com/auth/contacts"]

SECRETS = VAULT / "JamesOS" / "Secrets"
DATABASE = VAULT / "JamesOS" / "Database" / "google_contacts"
CREDENTIALS_FILE = SECRETS / "gmail_credentials.json"
TOKEN_FILE = SECRETS / "google_contacts_token.json"
CONTACTS_FILE = DATABASE / "contacts.json"


def _contacts_service():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("people", "v1", credentials=creds)


def _first(items, key="value"):
    if not items:
        return ""
    return items[0].get(key, "")


def import_google_contacts() -> str:
    cfg = get_config("google_contacts.yaml").get("google_contacts", {})
    max_results = int(cfg.get("max_results", 200))

    service = _contacts_service()
    DATABASE.mkdir(parents=True, exist_ok=True)

    response = service.people().connections().list(
        resourceName="people/me",
        pageSize=max_results,
        personFields="names,emailAddresses,phoneNumbers,birthdays,addresses,organizations,relations,biographies",
    ).execute()

    contacts = {}

    for person in response.get("connections", []):
        names = person.get("names", [])
        display_name = _first(names, "displayName")
        if not display_name:
            continue

        birthday = ""
        birthdays = person.get("birthdays", [])
        if birthdays:
            date = birthdays[0].get("date", {})
            year = date.get("year")
            month = date.get("month")
            day = date.get("day")
            if month and day:
                birthday = f"{year}-{month:02d}-{day:02d}" if year else f"--{month:02d}-{day:02d}"

        contacts[display_name] = {
            "source": "google_contacts",
            "resource_name": person.get("resourceName", ""),
            "relationship": "",
            "birthday": birthday,
            "phone": _first(person.get("phoneNumbers", [])),
            "email": _first(person.get("emailAddresses", [])),
            "address": _first(person.get("addresses", []), "formattedValue"),
            "organization": _first(person.get("organizations", []), "name"),
            "notes": _first(person.get("biographies", [])),
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    CONTACTS_FILE.write_text(json.dumps({"contacts": contacts}, indent=2), encoding="utf-8")
    return f"Imported {len(contacts)} Google contacts"
