from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

from jamesos.services import email_importer
from jamesos.services import memory_v2


def test_import_eml_uses_sent_date_and_extracts_entities(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    archive = tmp_path / "archive"
    brain = tmp_path / "brain"
    index = tmp_path / "index" / "outlook_email_index.jsonl"
    monkeypatch.setattr(email_importer, "ARCHIVE_ROOT", archive)
    monkeypatch.setattr(email_importer, "BRAIN_ROOT", brain)
    monkeypatch.setattr(email_importer, "INDEX_PATH", index)

    message = EmailMessage()
    message["Subject"] = "WGL paving ticket 88858"
    message["From"] = "Malcolm Example <malcolm@cgi.com>"
    message["To"] = "James Example <james@cgi.com>"
    message["Cc"] = "Kevin Example <kevin@example.com>"
    message["Date"] = "Tue, 14 Jan 2025 09:30:00 -0500"
    message["Message-ID"] = "<test-88858@example.com>"
    message.set_content("Please review Oracle work request 88858 for SFM2.")
    message.add_alternative("<p>Please review <b>ticket 88858</b>.</p>", subtype="html")
    message.add_attachment(b"attachment", maintype="application", subtype="octet-stream", filename="work.txt")
    eml_path = source / "message.eml"
    eml_path.write_bytes(message.as_bytes())

    result = email_importer.import_eml_directory(source)

    assert result["status"] == "ok"
    assert result["imported"] == 1
    raw_files = list((archive / "2025" / "01" / "14").glob("*.eml"))
    json_files = list((archive / "2025" / "01" / "14").glob("*.json"))
    markdown_files = list((brain / "2025" / "01" / "14").glob("*.md"))
    assert len(raw_files) == len(json_files) == len(markdown_files) == 1

    record = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert record["date_sent"] == "2025-01-14T09:30:00-05:00"
    assert record["entities"]["ticket_numbers"] == ["88858"]
    assert record["entities"]["projects"] == ["CGI/WGL"]
    assert {"CGI", "Oracle", "Paving", "SFM2", "WGL"}.issubset(
        record["entities"]["wgl_cgi_terms"]
    )
    assert record["attachments"][0]["filename"] == "work.txt"
    assert len(index.read_text(encoding="utf-8").splitlines()) == 1

    second_result = email_importer.import_eml_directory(source)
    assert second_result["imported"] == 1
    assert len(index.read_text(encoding="utf-8").splitlines()) == 1

    timeline = tmp_path / "timeline"
    monkeypatch.setattr(memory_v2, "EMAIL_ROOT", brain)
    monkeypatch.setattr(memory_v2, "TIMELINE_DIR", timeline)
    catalog = memory_v2._email_catalog()
    assert catalog[0]["people"] == ["James Example", "Kevin Example", "Malcolm Example"]
    assert catalog[0]["projects"] == ["CGI/WGL", "Paving"]
    assert catalog[0]["tickets"] == ["88858"]
    memory_v2._build_email_timeline(catalog)
    assert (timeline / "2025-01-14.md").exists()


def test_malformed_headers_and_address_groups_do_not_fail_import(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(email_importer, "ARCHIVE_ROOT", tmp_path / "archive")
    monkeypatch.setattr(email_importer, "BRAIN_ROOT", tmp_path / "brain")
    monkeypatch.setattr(email_importer, "INDEX_PATH", tmp_path / "index.jsonl")

    raw_to = "Team: Alice <alice@example.com>, Bob <bob@example.com>;"
    raw_cc = "Suarez, Luis; Allendoerfer, James R; Broken Recipient"
    raw_message = (
        "From: Sender <sender@example.com>\n"
        f"To: {raw_to}\n"
        f"Cc: {raw_cc}\n"
        "Date: Tue, 14 Jan 2025 09:30:00 -0500\n"
        "Subject: Malformed header regression\n"
        "Message-ID: <[broken@example.com]>\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Message body.\n"
    ).encode()
    (source / "malformed.eml").write_bytes(raw_message)

    result = email_importer.import_eml_directory(source)

    assert result["status"] == "ok"
    record_path = next((tmp_path / "archive").rglob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert [row["email"] for row in record["to"]] == [
        "alice@example.com",
        "bob@example.com",
    ]
    assert record["cc"] == [{"name": "", "email": "", "raw": raw_cc}]
    assert record["raw_address_headers"]["to"] == [raw_to]
    assert record["raw_address_headers"]["cc"] == [raw_cc]
    assert record["message_id"] == "<[broken@example.com]>"


def test_address_parser_falls_back_when_parser_raises(monkeypatch) -> None:
    raw = (
        "To: Person One <one@example.com>, malformed\n"
        "Date: Tue, 14 Jan 2025 09:30:00 -0500\n\n"
    ).encode()
    message = email_importer.BytesParser(policy=email_importer.policy.default).parsebytes(raw)

    def broken_getaddresses(values):
        raise IndexError("malformed address group")

    monkeypatch.setattr(email_importer, "getaddresses", broken_getaddresses)

    assert email_importer._addresses(message, "To") == [
        {"name": "", "email": "one@example.com"}
    ]


def test_invalid_unicode_surrogates_are_replaced() -> None:
    value = "before\udcffafter"

    assert email_importer._valid_unicode(value) == "before?after"
    assert email_importer._clean(value) == "before?after"
