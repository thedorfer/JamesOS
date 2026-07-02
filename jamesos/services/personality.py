from jamesos.config.loader import get_config


def jade_personality_prompt() -> str:
    cfg = get_config("personality.yaml")

    assistant = cfg.get("assistant", {})
    tone = cfg.get("tone", {})
    style = cfg.get("style", [])
    phrases = cfg.get("phrases", {})

    name = assistant.get("name", "Jade")
    role = assistant.get("role", "James's personal assistant")
    identity = assistant.get("identity", "")

    lines = [
        f"You are {name}, {role}.",
        f"Your vibe: {identity}.",
        "",
        "Personality:",
        f"- Warmth: {tone.get('warmth', 8)}/10",
        f"- Playfulness: {tone.get('playfulness', 8)}/10",
        f"- Sarcasm: {tone.get('sarcasm', 4)}/10",
        f"- Flirtiness: {tone.get('flirtiness', 3)}/10, light and tasteful only",
        f"- Confidence: {tone.get('confidence', 9)}/10",
        "",
        "Rules:",
    ]

    lines.extend([f"- {item}" for item in style])

    allowed = phrases.get("allowed", [])
    avoid = phrases.get("avoid", [])

    if allowed:
        lines.extend(["", "Natural phrases you may use:"])
        lines.extend([f"- {p}" for p in allowed])

    if avoid:
        lines.extend(["", "Avoid these phrases:"])
        lines.extend([f"- {p}" for p in avoid])

    return "\n".join(lines)
