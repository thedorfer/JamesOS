import shutil
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.inbox_cleanup import suggest_inbox_cleanup
from jamesos.services.refresh import refresh_dashboards


def archive_gmail_inbox_notes() -> str:
    inbox = VAULT / "00-Inbox"
    year = datetime.now().strftime("%Y")
    archive = VAULT / "Archive" / "Inbox" / "Gmail" / year
    archive.mkdir(parents=True, exist_ok=True)

    if not inbox.exists():
        return "Gmail archive plugin: inbox not found."

    moved = 0

    for path in sorted(inbox.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")

        is_gmail = (
            "Source: gmail" in text
            or "source: gmail" in text
            or "Gmail Thread ID:" in text
        )

        if not is_gmail:
            continue

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "Status: Archived" not in text:
            text += (
                "\n\n---\n"
                "JamesOS Processing\n"
                "Status: Archived\n"
                "Consumed: true\n"
                f"ArchivedAt: {now}\n"
                "ArchiveReason: Gmail source consumed\n"
            )
            path.write_text(text, encoding="utf-8")

        target = archive / path.name
        counter = 2
        while target.exists():
            target = archive / f"{path.stem} ({counter}){path.suffix}"
            counter += 1

        shutil.move(str(path), str(target))
        moved += 1

    if moved:
        suggest_inbox_cleanup()
        refresh_dashboards()

    return f"Gmail archive plugin: archived {moved} inbox notes."


def archive_calendar_inbox_notes() -> str:
    inbox = VAULT / "00-Inbox"
    year = datetime.now().strftime("%Y")
    archive = VAULT / "Archive" / "Inbox" / "Calendar" / year
    archive.mkdir(parents=True, exist_ok=True)

    if not inbox.exists():
        return "Calendar archive plugin: inbox not found."

    moved = 0

    for path in sorted(inbox.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")

        is_calendar = (
            "Source: google_calendar" in text
            or "source: google_calendar" in text
            or "Event ID:" in text
            or "Calendar:" in text
        )

        if not is_calendar:
            continue

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "Status: Archived" not in text:
            text += (
                "\n\n---\n"
                "JamesOS Processing\n"
                "Status: Archived\n"
                "Consumed: true\n"
                f"ArchivedAt: {now}\n"
                "ArchiveReason: Calendar source consumed\n"
            )
            path.write_text(text, encoding="utf-8")

        target = archive / path.name
        counter = 2
        while target.exists():
            target = archive / f"{path.stem} ({counter}){path.suffix}"
            counter += 1

        shutil.move(str(path), str(target))
        moved += 1

    if moved:
        suggest_inbox_cleanup()
        refresh_dashboards()

    return f"Calendar archive plugin: archived {moved} inbox notes."
