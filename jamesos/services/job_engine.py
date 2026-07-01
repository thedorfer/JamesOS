from datetime import datetime

from jamesos.plugins.registry import get_start_day_plugins, run_plugins


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
    return run_plugins(get_start_day_plugins())


def start_day_job() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return "\n".join([
        f"Start Day Job: {today}",
        refresh_all_job(),
    ])


def end_day_job() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return "\n".join([
        f"End Day Job: {today}",
        refresh_all_job(),
    ])
