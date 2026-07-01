from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT


KNOWLEDGE_ROOT = VAULT / "JamesOS" / "Knowledge"

DEFAULT_ENTITIES = {
    "People": [
        "Tom",
        "Ian",
        "Kevin",
        "Malcolm",
        "Luke",
        "Heather",
        "Ryan",
        "Luisa",
        "Martin",
        "Meenakshi",
    ],
    "Projects": [
        "Paving",
        "PowerPlan",
        "ERP Attribute Migration",
        "FERC",
        "CPMP",
        "Capital Work Order",
        "UOM Conversion",
    ],
    "Systems": [
        "WG_CUSTOM",
        "ARMEXT",
        "WMIS",
        "CC",
        "IMFGTW",
        "FMDR",
    ],
    "Environments": [
        "SFM2",
        "SBX",
        "R2QA",
        "OG36DEV2",
    ],
    "Customers": [
        "WGL",
        "PPL",
    ],
}


def _write_entity(category: str, name: str) -> None:
    folder = KNOWLEDGE_ROOT / category
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{name}.md"

    if path.exists():
        return

    now = datetime.now().strftime("%Y-%m-%d")

    path.write_text(
        f"""# {name}

Type: {category}
Created: {now}
Status: active

## Summary

## Related Work

## Notes

""",
        encoding="utf-8",
    )


def initialize_knowledge_base() -> str:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)

    for category, names in DEFAULT_ENTITIES.items():
        for name in names:
            _write_entity(category, name)

    return f"Initialized knowledge base at {KNOWLEDGE_ROOT}"
