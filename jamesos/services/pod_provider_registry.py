from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


REGISTRY_PATH = VAULT / "JamesOS" / "POD" / "pod_provider_registry.yaml"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "POD Provider Registry.md"

DEFAULT_PROVIDERS: dict[str, dict[str, Any]] = {
    "printify": {
        "provider_id": "printify",
        "display_name": "Printify",
        "enabled": True,
        "readonly": True,
        "writes_enabled": False,
        "draft_creation_enabled": False,
        "order_enabled": False,
        "supported_product_types": ["shirts", "shirt", "hoodies", "hoodie", "mugs", "mug", "totes", "stickers", "accessories"],
        "api_base_url": "",
        "api_key_configured": False,
        "notes": "Configured as a future approval-first POD provider. API writes remain disabled.",
        "status": "readonly_foundation",
    },
    "inkedjoy": {
        "provider_id": "inkedjoy",
        "display_name": "InkedJoy",
        "enabled": True,
        "readonly": True,
        "writes_enabled": False,
        "draft_creation_enabled": False,
        "order_enabled": False,
        "supported_product_types": [
            "womens_underwear",
            "panties",
            "panty",
            "thong",
            "thongs",
            "shirts",
            "shirt",
            "hoodies",
            "hoodie",
            "mugs",
            "mug",
            "totes",
            "accessories",
        ],
        "api_base_url": "",
        "api_key_configured": False,
        "notes": "API access not confirmed; manual upload/draft-ready mode only.",
        "status": "manual_upload_ready_foundation",
    },
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def initialize_provider_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not registry_path.exists():
        registry_path.write_text(yaml.safe_dump({"providers": DEFAULT_PROVIDERS}, sort_keys=False), encoding="utf-8")
        created = True
    return {"status": "ok", "created": created, "registry_path": str(registry_path)}


def load_provider_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    initialize_provider_registry(registry_path)
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    loaded_providers = loaded.get("providers") or {}
    providers = {
        provider_id: {**DEFAULT_PROVIDERS.get(provider_id, {}), **provider}
        for provider_id, provider in {**DEFAULT_PROVIDERS, **loaded_providers}.items()
    }
    for provider in providers.values():
        provider["readonly"] = True
        provider["writes_enabled"] = False
        provider["draft_creation_enabled"] = False
        provider["order_enabled"] = False
    return {"providers": providers}


def list_providers(path: Path | None = None) -> dict[str, Any]:
    providers = list(load_provider_registry(path)["providers"].values())
    return {
        "status": "ok",
        "providers": providers,
        "provider_count": len(providers),
        "enabled_provider_count": len([item for item in providers if item.get("enabled")]),
        "readonly": True,
        "writes_enabled": False,
        "draft_creation_enabled": False,
        "order_enabled": False,
    }


def get_provider(provider_id: str, path: Path | None = None) -> dict[str, Any]:
    providers = load_provider_registry(path)["providers"]
    key = provider_id.strip().lower()
    provider = providers.get(key)
    if provider is None:
        for item in providers.values():
            if str(item.get("display_name", "")).strip().lower() == key:
                provider = item
                break
    if provider is None:
        raise KeyError(f"Unknown POD provider: {provider_id}")
    return provider


def provider_health(path: Path | None = None) -> dict[str, Any]:
    initialize_provider_registry(path)
    providers = list_providers(path)
    return {
        "status": "ok",
        "registry_path": str(path or REGISTRY_PATH),
        "provider_count": providers["provider_count"],
        "enabled_provider_count": providers["enabled_provider_count"],
        "providers": [item["provider_id"] for item in providers["providers"]],
        "readonly": True,
        "writes_enabled": False,
        "draft_creation_enabled": False,
        "order_enabled": False,
        "external_calls_enabled": False,
    }


def write_provider_report(path: Path | None = None, report_path: Path | None = None) -> dict[str, Any]:
    report = report_path or REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    providers = list_providers(path)["providers"]
    lines = [
        "# POD Provider Registry",
        "",
        f"Updated: {_now()}",
        "",
        "## Safety",
        "",
        "- Read-only foundation only.",
        "- External writes, draft creation, uploads, orders, and publishing are disabled.",
        "- InkedJoy is currently manual upload/draft-ready mode only.",
        "",
        "## Providers",
        "",
    ]
    for provider in providers:
        lines.extend([
            f"### {provider.get('display_name')}",
            "",
            f"- Provider ID: {provider.get('provider_id')}",
            f"- Enabled: {provider.get('enabled')}",
            f"- Read-only: {provider.get('readonly')}",
            f"- Writes enabled: {provider.get('writes_enabled')}",
            f"- Draft creation enabled: {provider.get('draft_creation_enabled')}",
            f"- Order enabled: {provider.get('order_enabled')}",
            f"- Notes: {provider.get('notes')}",
            "",
        ])
    report.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report_path": str(report), "provider_count": len(providers)}
