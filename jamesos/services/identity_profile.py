from __future__ import annotations

from jamesos.services.world_model import load_world_model


def identity_context() -> str:
    data = load_world_model()
    owner = data.get("owner", {})
    preferred_name = owner.get("preferred_name") or owner.get("name") or "James"
    lines = [
        "# Identity Context",
        f"James is the user. His name is {preferred_name}.",
        "Do not describe James Allendoerfer as a random third party.",
        "Treat James as the person asking and the subject of personal context.",
        "If the question is about James, answer from his first-person perspective when appropriate.",
    ]
    return "\n".join(lines)
