from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PluginStep:
    name: str
    run: Callable[[], str]
    enabled: bool = True


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

    return [
        PluginStep("database", build_database),
        PluginStep("brain_reports", generate_brain_reports),
        PluginStep("knowledge_pages", update_knowledge_pages),
        PluginStep("timeline", build_timeline),
        PluginStep("search", build_search_index),
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
        if not plugin.enabled:
            results.append(f"Skipped plugin: {plugin.name}")
            continue

        try:
            result = plugin.run()
            results.append(result)
        except Exception as exc:
            results.append(f"Plugin failed: {plugin.name}: {exc}")
            raise

    return "\n".join(results)
