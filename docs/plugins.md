# JamesOS Plugin Architecture

JamesOS jobs are now pipeline-driven.

The plugin registry lives here:

    jamesos/plugins/registry.py

Start Day currently runs these plugin steps:

    database
    brain_reports
    knowledge_pages
    timeline
    search
    inbox_review
    inbox_cleanup
    daily_briefing
    work_intelligence
    status_report
    dashboards

To add a new capability, create or reuse a service function, then register it as a PluginStep in get_start_day_plugins().

This keeps the job engine small and makes future integrations easier.

Future integration plugins may include:

    gmail_import
    outlook_import
    calendar_import
    file_watch
    clipboard_watch
    phone_capture
