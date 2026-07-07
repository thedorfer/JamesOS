from __future__ import annotations

from pathlib import Path
from typing import Any

from jamesos.config import VAULT


ASSET_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Assets"
ASSET_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ttf", ".otf", ".ai", ".eps", ".pdf"}
FONT_EXTENSIONS = {".ttf", ".otf"}
METADATA_ONLY_EXTENSIONS = FONT_EXTENSIONS | {".ai", ".eps", ".pdf"}


def initialize_asset_library(root: Path | None = None) -> dict[str, Any]:
    asset_root = root or ASSET_ROOT
    asset_root.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "root": str(asset_root), "execution_enabled": False}


def _asset_record(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    asset_type = "font" if suffix in FONT_EXTENSIONS else suffix.lstrip(".")
    return {
        "name": path.stem,
        "extension": suffix,
        "asset_type": asset_type,
        "path": str(path) if suffix not in FONT_EXTENSIONS else "",
        "file_size_bytes": size,
        "metadata_only": suffix in METADATA_ONLY_EXTENSIONS,
        "content_included": False,
        "execution_enabled": False,
    }


def scan_assets(root: Path | None = None) -> dict[str, Any]:
    asset_root = root or ASSET_ROOT
    initialize_asset_library(asset_root)
    assets = [
        _asset_record(path)
        for path in sorted(asset_root.rglob("*"))
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS
    ]
    return {
        "status": "ok",
        "root": str(asset_root),
        "assets": assets,
        "asset_count": len(assets),
        "metadata_only": True,
        "execution_enabled": False,
    }


def suggest_assets(package: dict[str, Any], limit: int = 5, root: Path | None = None) -> list[dict[str, Any]]:
    assets = scan_assets(root)["assets"]
    text = " ".join(str(package.get(key, "")) for key in ["brand_id", "niche", "style", "product_type", "title"]).lower()
    scored = []
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        score = sum(1 for token in text.split() if token and token in name)
        scored.append((score, asset))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [asset for _score, asset in scored[:limit]]
