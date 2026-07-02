from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jamesos.config import VAULT

WORLD_MODEL_FILE = VAULT / "JamesOS" / "Brain" / "world_model.json"

DEFAULT_WORLD_MODEL: dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "owner": {
        "name": "James Allendoerfer",
        "preferred_name": "James",
        "roles": [
            "Integration Developer",
            "CGI software developer / consultant",
            "GCU instructor",
            "JamesOS builder",
        ],
    },
    "family": [
        {
            "name": "Jidapa",
            "relationship": "wife",
            "confidence": "verified",
            "notes": ["Use as spouse/wife in family context."],
        },
        {
            "name": "Daughter 1",
            "relationship": "daughter",
            "confidence": "placeholder",
            "notes": ["Name intentionally not assumed yet."],
        },
        {
            "name": "Daughter 2",
            "relationship": "daughter",
            "confidence": "placeholder",
            "notes": ["Name intentionally not assumed yet."],
        },
    ],
    "people": {
        "Kevin": {
            "domain": "work",
            "relationship": "work contact",
            "confidence": "current_context",
            "notes": ["Often appears in paving / WR Type testing context."],
        },
        "Malcolm": {
            "domain": "work",
            "relationship": "work contact / SME",
            "confidence": "current_context",
            "notes": ["Often appears in paving context."],
        },
        "Tom": {
            "domain": "work",
            "relationship": "work contact",
            "confidence": "current_context",
            "notes": ["Used for confirmations/status in work context."],
        },
        "Ian": {
            "domain": "work",
            "relationship": "work contact",
            "confidence": "current_context",
            "notes": ["Used for work ticket/status communication."],
        },
    },
    "rules": [
        "Treat this file as higher trust than search indexes, old reports, memory snippets, and graph matches.",
        "Do not infer family relationships from historical tickets, random people index rows, or stale graph matches.",
        "If a family name is unknown, say it is not verified instead of guessing.",
        "Prefer current verified facts over old indexed documents.",
    ],
}


def ensure_world_model() -> dict[str, Any]:
    WORLD_MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not WORLD_MODEL_FILE.exists():
        WORLD_MODEL_FILE.write_text(json.dumps(DEFAULT_WORLD_MODEL, indent=2), encoding="utf-8")
        return DEFAULT_WORLD_MODEL
    return load_world_model()


def load_world_model() -> dict[str, Any]:
    if not WORLD_MODEL_FILE.exists():
        return ensure_world_model()
    try:
        data = json.loads(WORLD_MODEL_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return DEFAULT_WORLD_MODEL
        return data
    except Exception:
        return DEFAULT_WORLD_MODEL


def world_model_summary(mode: str | None = None) -> str:
    data = load_world_model()
    mode_value = (mode or "personal").lower()

    lines = [
        "# Verified World Model",
        "This is high-trust context. Prefer it over stale search/index/graph matches.",
        "",
    ]

    owner = data.get("owner", {})
    if owner:
        lines.extend([
            "## Owner",
            f"Name: {owner.get('name', 'James')}",
            f"Preferred name: {owner.get('preferred_name', 'James')}",
            "Roles: " + ", ".join(owner.get("roles", [])),
            "",
        ])

    if mode_value in {"family", "personal"}:
        lines.append("## Verified family")
        for person in data.get("family", []):
            notes = "; ".join(person.get("notes", []))
            lines.append(
                f"- {person.get('name')}: {person.get('relationship')} "
                f"({person.get('confidence', 'unknown')}). {notes}"
            )
        lines.append("")

    if mode_value in {"work", "personal", "jamesos"}:
        lines.append("## Verified/current people")
        people = data.get("people", {})
        for name, person in people.items():
            if mode_value == "work" and person.get("domain") != "work":
                continue
            notes = "; ".join(person.get("notes", []))
            lines.append(
                f"- {name}: {person.get('relationship')} / {person.get('domain')} "
                f"({person.get('confidence', 'unknown')}). {notes}"
            )
        lines.append("")

    rules = data.get("rules", [])
    if rules:
        lines.append("## Trust rules")
        for rule in rules:
            lines.append(f"- {rule}")

    return "\n".join(lines)


def world_model_dashboard_cards(mode: str | None = None) -> list[dict[str, str]]:
    data = load_world_model()
    mode_value = (mode or "personal").lower()
    cards: list[dict[str, str]] = []

    if mode_value in {"family", "personal"}:
        family = data.get("family", [])
        verified = [p for p in family if p.get("confidence") == "verified"]
        placeholders = [p for p in family if p.get("confidence") != "verified"]
        body = f"Verified: {len(verified)}. Placeholders to confirm: {len(placeholders)}."
        cards.append({
            "title": "Verified family model",
            "body": body,
            "kind": "world",
            "prompt": "Summarize my verified family model and tell me what is still missing.",
        })

    if mode_value in {"work", "personal", "jamesos"}:
        people = data.get("people", {})
        work_people = [name for name, p in people.items() if p.get("domain") == "work"]
        if work_people:
            cards.append({
                "title": "Current work contacts",
                "body": ", ".join(work_people[:6]),
                "kind": "world",
                "prompt": "Summarize my current verified work contacts and what each is connected to.",
            })

    return cards
