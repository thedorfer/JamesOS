from datetime import datetime

from jamesos.config import VAULT
from jamesos.config.loader import get_config
from jamesos.services.agent import ask_agent


REPORTS = VAULT / "JamesOS" / "Reports"


DEFAULT_QUESTIONS = [
    "What should I pay attention to today?",
    "What work items look important?",
]


def generate_proactive_briefing() -> str:
    cfg = get_config("proactive.yaml").get("proactive", {})

    use_ai = bool(cfg.get("use_ai", True))
    max_ai_questions = int(cfg.get("max_ai_questions", 1))
    questions = cfg.get("questions", DEFAULT_QUESTIONS)

    REPORTS.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Proactive Assistant",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"AI Enabled: {use_ai}",
        f"Max AI Questions: {max_ai_questions}",
        "",
    ]

    ai_used = 0

    for question in questions:
        lines.extend([f"## {question}", ""])

        try:
            allow_ai = use_ai and ai_used < max_ai_questions
            result = ask_agent(question, use_ai=allow_ai)

            if allow_ai:
                ai_used += 1

            lines.append(result["answer"])
        except Exception as exc:
            lines.append(f"Failed: {exc}")

        lines.append("")

    path = REPORTS / "Proactive Assistant.md"
    path.write_text("\n".join(lines), encoding="utf-8")

    return f"Wrote proactive assistant report: {path.relative_to(VAULT)}"
