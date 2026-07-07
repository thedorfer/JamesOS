from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


CONFIG_ROOT = VAULT / "JamesOS" / "Config"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Server Configuration.md"

SERVER_CONFIG = "server.yaml"
INTEGRATIONS_CONFIG = "integrations.yaml"

DEFAULT_SERVER_CONFIG = {
    "version": 1,
    "server": {
        "name": "JamesOS API",
        "host": "0.0.0.0",
        "port": 8787,
        "public_base_url": "http://localhost:8787",
        "require_api_key": True,
    },
    "health": {
        "check_paths": True,
        "check_integrations": True,
        "write_report": True,
    },
}

DEFAULT_INTEGRATIONS_CONFIG = {
    "version": 1,
    "integrations": {
        "jade_app": {
            "enabled": True,
            "status": "local_client",
            "notes": "Flutter Jade client for Linux and Android.",
        },
        "tasker_phone_ingestion": {
            "enabled": True,
            "status": "configured_by_user",
            "endpoint": "/phone-ingest",
            "notes": "Android Tasker posts phone events to JamesOS with the API key.",
        },
        "comfyui": {
            "enabled": False,
            "status": "planned_local_only",
            "api_url": "http://localhost:8188",
            "gpu_target": "GTX 1080 Ti",
            "execution_enabled": False,
            "notes": "Future local image engine. JamesOS does not call ComfyUI yet.",
        },
        "printify": {
            "enabled": False,
            "status": "planned_draft_only",
            "execution_enabled": False,
            "publish_enabled": False,
            "notes": "Future draft target only. No products are created or published yet.",
        },
        "etsy": {
            "enabled": False,
            "status": "planned_approval_required",
            "execution_enabled": False,
            "publish_enabled": False,
            "notes": "Future sales platform. No live listings are created yet.",
        },
        "unitystitches": {
            "enabled": False,
            "status": "roadmap",
            "draft_only": True,
            "approval_required": True,
            "notes": "Future daily product draft pipeline.",
        },
    },
    "safety": {
        "approval_first": True,
        "no_publish_without_approval": True,
        "no_orders_without_approval": True,
        "no_send_to_production_without_approval": True,
    },
}


def _write_default(path: Path, data: dict[str, Any]) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return True


def initialize_server_config() -> dict[str, Any]:
    created = []
    if _write_default(CONFIG_ROOT / SERVER_CONFIG, DEFAULT_SERVER_CONFIG):
        created.append(SERVER_CONFIG)
    if _write_default(CONFIG_ROOT / INTEGRATIONS_CONFIG, DEFAULT_INTEGRATIONS_CONFIG):
        created.append(INTEGRATIONS_CONFIG)
    return {"status": "ok", "created": created}


def _load_yaml(filename: str, default: dict[str, Any]) -> dict[str, Any]:
    initialize_server_config()
    path = CONFIG_ROOT / filename
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    return loaded or default


def server_config() -> dict[str, Any]:
    return _load_yaml(SERVER_CONFIG, DEFAULT_SERVER_CONFIG)


def integrations_config() -> dict[str, Any]:
    return _load_yaml(INTEGRATIONS_CONFIG, DEFAULT_INTEGRATIONS_CONFIG)


def integration_health() -> dict[str, Any]:
    data = integrations_config()
    rows = []
    for name, config in sorted(data.get("integrations", {}).items()):
        enabled = bool(config.get("enabled", False))
        execution_enabled = bool(config.get("execution_enabled", enabled))
        publish_enabled = bool(config.get("publish_enabled", False))
        rows.append({
            "name": name,
            "enabled": enabled,
            "execution_enabled": execution_enabled,
            "publish_enabled": publish_enabled,
            "status": config.get("status", "unknown"),
            "safe": not publish_enabled,
            "notes": config.get("notes", ""),
        })
    return {"status": "ok", "integrations": rows, "safety": data.get("safety", {})}


def service_health() -> dict[str, Any]:
    initialize_server_config()
    queue_root = VAULT / "JamesOS" / "Queue"
    reports_root = VAULT / "JamesOS" / "Reports"
    checks = {
        "data_root": {"path": str(VAULT), "exists": VAULT.exists()},
        "config_root": {"path": str(CONFIG_ROOT), "exists": CONFIG_ROOT.exists()},
        "queue_root": {"path": str(queue_root), "exists": queue_root.exists()},
        "reports_root": {"path": str(reports_root), "exists": reports_root.exists()},
        "server_config": {"path": str(CONFIG_ROOT / SERVER_CONFIG), "exists": (CONFIG_ROOT / SERVER_CONFIG).exists()},
        "integrations_config": {
            "path": str(CONFIG_ROOT / INTEGRATIONS_CONFIG),
            "exists": (CONFIG_ROOT / INTEGRATIONS_CONFIG).exists(),
        },
    }
    return {
        "status": "ok" if all(item["exists"] for item in checks.values()) else "degraded",
        "checks": checks,
        "integrations": integration_health(),
    }


def write_server_config_report() -> dict[str, Any]:
    health = service_health()
    server = server_config().get("server", {})
    integrations = health.get("integrations", {}).get("integrations", [])
    lines = [
        "# Server Configuration",
        "",
        f"Status: {health['status']}",
        "",
        "## API",
        "",
        f"- Name: {server.get('name', 'JamesOS API')}",
        f"- Host: {server.get('host', '')}",
        f"- Port: {server.get('port', '')}",
        f"- API key required: {server.get('require_api_key', True)}",
        "",
        "## Local Paths",
        "",
    ]
    for name, check in health["checks"].items():
        state = "ok" if check["exists"] else "missing"
        lines.append(f"- {name}: {state}")

    lines.extend(["", "## Integrations", ""])
    for item in integrations:
        state = "enabled" if item["enabled"] else "disabled"
        safety = "safe" if item["safe"] else "unsafe"
        lines.append(f"- {item['name']}: {state}, {item['status']}, {safety}")

    lines.extend([
        "",
        "## Safety",
        "",
        "- Printify execution is not implemented here.",
        "- Etsy execution is not implemented here.",
        "- ComfyUI execution is not implemented here.",
        "- Publishing, orders, sending, and production require James approval.",
        "",
    ])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report": str(REPORT_PATH), "health": health}
