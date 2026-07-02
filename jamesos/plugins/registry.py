from dataclasses import dataclass
from typing import Callable

from jamesos.config.loader import plugin_enabled


@dataclass(frozen=True)
class PluginStep:
    name: str
    run: Callable[[], str]


def get_start_day_plugins() -> list[PluginStep]:
    from jamesos.services.database import build_database
    from jamesos.services.brain_reports import generate_brain_reports
    from jamesos.services.knowledge_service import update_knowledge_pages
    from jamesos.services.timeline import build_timeline
    from jamesos.services.search_service import build_search_index
    from jamesos.services.inbox_review import review_inbox
    from jamesos.services.inbox_cleanup import suggest_inbox_cleanup
    from jamesos.services.briefing import generate_daily_briefing
    from jamesos.services.work_intelligence import generate_work_intelligence
    from jamesos.services.status_report import generate_status_report
    from jamesos.services.refresh import refresh_dashboards
    from jamesos.integrations.gmail_importer import import_gmail_label

    return [
        PluginStep("database", build_database),
        PluginStep("brain_reports", generate_brain_reports),
        PluginStep("knowledge_pages", update_knowledge_pages),
        PluginStep("timeline", build_timeline),
        PluginStep("search", build_search_index),
        PluginStep("gmail", import_gmail_label),
        PluginStep("inbox_review", review_inbox),
        PluginStep("inbox_cleanup", suggest_inbox_cleanup),
        PluginStep("daily_briefing", generate_daily_briefing),
        PluginStep("work_intelligence", generate_work_intelligence),
        PluginStep("status_report", generate_status_report),
        PluginStep("dashboards", refresh_dashboards),
    ]


def run_plugins(plugins: list[PluginStep]) -> str:
    results = []

    for plugin in plugins:
        if not plugin_enabled(plugin.name):
            results.append(f"Skipped plugin: {plugin.name}")
            continue

        result = plugin.run()
        results.append(result)

    return "\n".join(results)
