from jamesos.services.dashboard import generate_home_dashboard
from jamesos.services.work_dashboard import generate_work_dashboard

def refresh_dashboards() -> str:
    home = generate_home_dashboard()
    work = generate_work_dashboard()
    return f"{home}\n{work}"
