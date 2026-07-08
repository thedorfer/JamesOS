from __future__ import annotations

from typing import Any


SAFETY = {
    "deletes_phone_data": False,
    "sends_messages": False,
    "cloud_upload_default": False,
    "requires_tasker": False,
    "provider_writes_enabled": False,
}

METHODS = [
    {
        "id": "linux_mtp_pull",
        "name": "Android USB/MTP pull from Linux Mint",
        "platform": "Linux Mint desktop/laptop",
        "summary": "Mount the phone over USB/MTP and copy screenshots, photos, exports, and app-export folders into JamesOS intake storage.",
        "deletes_phone_data": False,
        "sends_messages": False,
        "cloud_upload_default": False,
    },
    {
        "id": "syncthing",
        "name": "Syncthing folder sync",
        "platform": "Android + Linux Mint",
        "summary": "Sync selected phone folders to a local laptop folder that JamesOS can watch or import.",
        "deletes_phone_data": False,
        "sends_messages": False,
        "cloud_upload_default": False,
    },
    {
        "id": "kde_connect",
        "name": "KDE Connect",
        "platform": "Android + Linux desktop",
        "summary": "Use KDE Connect for local-network file sharing and notification visibility, then ingest exported files locally.",
        "deletes_phone_data": False,
        "sends_messages": False,
        "cloud_upload_default": False,
    },
    {
        "id": "adb_pull",
        "name": "ADB pull",
        "platform": "Android developer bridge",
        "summary": "Use read-only pull commands for screenshots, photos, downloads, and app exports when USB debugging is intentionally enabled.",
        "deletes_phone_data": False,
        "sends_messages": False,
        "cloud_upload_default": False,
    },
    {
        "id": "tasker_optional",
        "name": "Tasker optional push",
        "platform": "Android automation",
        "summary": "Tasker can still POST phone events, but it is optional rather than required.",
        "deletes_phone_data": False,
        "sends_messages": False,
        "cloud_upload_default": False,
    },
]


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "phone_ingestion",
        "method_count": len(METHODS),
        "safety": SAFETY,
    }


def methods() -> dict[str, Any]:
    return {
        "status": "ok",
        "methods": METHODS,
        "method_count": len(METHODS),
        "safety": SAFETY,
    }
