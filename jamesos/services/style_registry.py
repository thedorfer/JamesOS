from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


STYLE_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Styles"

STYLE_NAMES = ["typography", "retro", "minimalist", "cute", "bold", "watercolor", "vintage", "sticker", "pride", "Thai/English"]

DEFAULT_STYLES = {
    name.lower().replace("/", "_"): {
        "name": name.lower().replace("/", "_"),
        "display_name": name,
        "description": f"{name} visual direction for local draft planning.",
        "enabled": False,
        "execution_enabled": False,
    }
    for name in STYLE_NAMES
}


def initialize_style_registry(root: Path | None = None) -> dict[str, Any]:
    style_root = root or STYLE_ROOT
    style_root.mkdir(parents=True, exist_ok=True)
    created = []
    for name, style in DEFAULT_STYLES.items():
        path = style_root / f"{name}.yaml"
        if not path.exists():
            path.write_text(yaml.safe_dump(style, sort_keys=False), encoding="utf-8")
            created.append(name)
    return {"status": "ok", "root": str(style_root), "created": created}


def list_styles(root: Path | None = None) -> dict[str, Any]:
    style_root = root or STYLE_ROOT
    initialize_style_registry(style_root)
    styles = {}
    for path in sorted(style_root.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        name = str(data.get("name") or path.stem)
        styles[name] = {**DEFAULT_STYLES.get(name, {}), **data, "enabled": False, "execution_enabled": False}
    return {"status": "ok", "root": str(style_root), "styles": styles, "style_count": len(styles), "execution_enabled": False}


def get_style(style_name: str, root: Path | None = None) -> dict[str, Any]:
    key = style_name.lower().replace("/", "_").replace(" ", "_")
    styles = list_styles(root)["styles"]
    style = styles.get(key) or styles.get(style_name)
    if style is None:
        raise KeyError(f"Unknown style: {style_name}")
    return {"status": "ok", "style": style, "execution_enabled": False}


def select_style(package: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    text = " ".join(str(package.get(key, "")) for key in ["style", "niche", "title", "design_prompt"]).lower()
    if "thai" in text:
        name = "thai_english"
    elif "pride" in text or "lgbtq" in text or "trans" in text:
        name = "pride"
    elif "sticker" in text:
        name = "sticker"
    elif "retro" in text:
        name = "retro"
    elif "cute" in text:
        name = "cute"
    elif "watercolor" in text:
        name = "watercolor"
    elif "vintage" in text:
        name = "vintage"
    elif "minimal" in text:
        name = "minimalist"
    elif "typography" in text or "shirt" in text:
        name = "typography"
    else:
        name = "bold"
    return get_style(name, root)["style"]

