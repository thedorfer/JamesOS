from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.agent import ask_agent

REPORTS = VAULT / "JamesOS" / "Reports"


QUESTIONS = [
    "What should I pay attention to today?",
    "What work items look important?",
    "What do I need to know from Gmail and GCU?",
    "What calendar or travel items look important?",
]


def generate_proactive_briefing() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Proactive Assistant",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for question in QUESTIONS:
        lines.extend([
            f"## {question}",
            "",
        ])

        try:
            result = ask_agent(question, use_ai=True)
            lines.append(result["answer"])
        except Exception as exc:
            lines.append(f"Failed: {exc}")

        lines.append("")

    path = REPORTS / "Proactive Assistant.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote proactive assistant report: {path.relative_to(VAULT)}"
