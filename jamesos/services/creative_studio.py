from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreativeStudioPlan:
    name: str
    status: str
    next_phase: str
    notes: list[str]


def creative_studio_status() -> dict[str, Any]:
    plan = CreativeStudioPlan(
        name="Jade Creative Studio",
        status="roadmap_only",
        next_phase="Connect approved jobs to draft creative workflows.",
        notes=[
            "Job Queue is the automation backbone.",
            "Creative generation remains approval-first.",
            "No image generation, Printify, Etsy, publishing, ordering, or sending is active in Phase 1.",
        ],
    )
    return {
        "name": plan.name,
        "status": plan.status,
        "next_phase": plan.next_phase,
        "notes": plan.notes,
    }
