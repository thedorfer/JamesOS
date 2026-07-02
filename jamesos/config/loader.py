from pathlib import Path
import yaml

from jamesos.config import VAULT

CONFIG_ROOT = VAULT / "JamesOS" / "Config"

DEFAULT_CONFIG = {
    "system.yaml": """version: 1
profile: home

vault:
  refresh_on_start: true

daemon:
  enabled: true
  interval_seconds: 30

logging:
  level: INFO
""",
    "plugins.yaml": """version: 1

plugins:
  database:
    enabled: true
  brain_reports:
    enabled: true
  knowledge_pages:
    enabled: true
  timeline:
    enabled: true
  search:
    enabled: true
  inbox_review:
    enabled: true
  inbox_cleanup:
    enabled: true
  daily_briefing:
    enabled: true
  work_intelligence:
    enabled: true
  status_report:
    enabled: true
  dashboards:
    enabled: true

  gmail:
    enabled: false
  outlook:
    enabled: false
  calendar:
    enabled: false
  clipboard_watcher:
    enabled: false
  file_watcher:
    enabled: false
  screenshot_watcher:
    enabled: false
""",
    "intake.yaml": """version: 1

queue:
  retry_count: 3
  retry_delay_seconds: 30
  daemon_interval_seconds: 30

cleanup:
  auto_cleanup: false
  create_suggestions: true

capture:
  create_inbox_note: true
  refresh_dashboards: true
""",
    "folders.yaml": """version: 1

folders:
  inbox: "00-Inbox"
  intake: "JamesOS/Intake"
  queue: "JamesOS/Queue"
  reports: "JamesOS/Reports"
  database: "JamesOS/Database"
  knowledge: "JamesOS/Knowledge"

watch:
  downloads: "~/Downloads"
  desktop: "~/Desktop"
  screenshots: "~/Pictures/Screenshots"
""",
    "ai.yaml": """version: 1

memory:
  max_related_entities: 20

context:
  preview_length: 1200

recommendations:
  max_items: 15

search:
  default_limit: 10

assistant:
  personality: professional
  include_work: true
  include_personal: true
  include_gcu: true
  include_unitystitches: true
""",
}


def initialize_config() -> str:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)

    created = []
    for filename, content in DEFAULT_CONFIG.items():
        path = CONFIG_ROOT / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(filename)

    return "Created config files: " + ", ".join(created) if created else "Config files already exist"


def _load_yaml(filename: str) -> dict:
    initialize_config()
    path = CONFIG_ROOT / filename
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def get_config(filename: str) -> dict:
    return _load_yaml(filename)


def plugin_enabled(name: str) -> bool:
    data = _load_yaml("plugins.yaml")
    return bool(data.get("plugins", {}).get(name, {}).get("enabled", False))


def daemon_interval_seconds() -> int:
    data = _load_yaml("intake.yaml")
    return int(data.get("queue", {}).get("daemon_interval_seconds", 30))


def folder_path(name: str) -> Path:
    data = _load_yaml("folders.yaml")
    folder = data.get("folders", {}).get(name)
    return VAULT / folder if folder else VAULT / name


def watch_folder(name: str) -> Path:
    data = _load_yaml("folders.yaml")
    folder = data.get("watch", {}).get(name, "")
    return Path(folder).expanduser() if folder else Path.home() / name
