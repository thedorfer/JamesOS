from pathlib import Path

from jamesos.config import VAULT


CATEGORY_PATHS = {
    "people": "JamesOS/Knowledge/People",
    "customers": "JamesOS/Knowledge/Customers",
    "environments": "JamesOS/Knowledge/Environments",
    "systems": "JamesOS/Knowledge/Systems",
    "projects": "JamesOS/Knowledge/Projects",
}


def wiki_link(category: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""

    base = CATEGORY_PATHS.get(category.lower())
    if not base:
        return value

    return f"[[{base}/{value}|{value}]]"


def people_links(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""

    separators = ["/", ",", " and "]
    names = [value]

    for sep in separators:
        if sep in value:
            names = [part.strip() for part in value.split(sep) if part.strip()]
            break

    return " / ".join(wiki_link("people", name) for name in names)


def ensure_knowledge_page(category: str, value: str) -> None:
    value = (value or "").strip()
    if not value:
        return

    folder = CATEGORY_PATHS.get(category.lower())
    if not folder:
        return

    path = VAULT / folder / f"{value}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(
            f"# {value}\n\n"
            f"Type: {category.title()}\n"
            "Status: active\n\n"
            "## Summary\n\n"
            "## Mentioned In\n\n"
            "## Related Work\n\n"
            "## Notes\n",
            encoding="utf-8",
        )
