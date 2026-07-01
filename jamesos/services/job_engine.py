from datetime import datetime

from jamesos.services.database import build_database
from jamesos.services.knowledge_service import update_knowledge_pages
from jamesos.services.timeline import build_timeline
from jamesos.services.search_service import build_search_index
from jamesos.services.inbox_review import review_inbox
from jamesos.services.refresh import refresh_dashboards
from jamesos.services.briefing import generate_daily_briefing
from jamesos.services.work_intelligence import generate_work_intelligence
from jamesos.services.status_report import generate_status_report
from jamesos.services.memory_engine import build_memory
from jamesos.services.inbox_cleanup import suggest_inbox_cleanup


def run_job(job_name: str) -> str:
    job = job_name.strip().lower().replace(" ", "_")

    if job == "start_day":
        return start_day_job()

    if job == "end_day":
        return end_day_job()

    if job == "refresh_all":
        return refresh_all_job()

    return f"Unknown job: {job_name}"


def refresh_all_job() -> str:
    results = [
        build_database(),
        build_memory(),
        update_knowledge_pages(),
        build_timeline(),
        build_search_index(),
        review_inbox(),
        suggest_inbox_cleanup(),
        generate_daily_briefing(),
        generate_work_intelligence(),
        generate_status_report(),
        refresh_dashboards(),
    ]

    return "\n".join(results)


def start_day_job() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    results = [
        f"Start Day Job: {today}",
        refresh_all_job(),
    ]

    return "\n".join(results)


def end_day_job() -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    results = [
        f"End Day Job: {today}",
        refresh_all_job(),
    ]

    return "\n".join(results)
