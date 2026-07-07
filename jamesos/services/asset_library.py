from __future__ import annotations

from pathlib import Path
from typing import Any

from jamesos.config import VAULT


ASSET_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Assets"
BRAND_ASSETS_ROOT = VAULT / "JamesOS" / "Brands"
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
    lower_name = path.stem.lower()
    role = "logo" if "logo" in lower_name else ("flag" if any(token in lower_name for token in ["pride", "rainbow", "trans", "intersex", "lgbtq", "flag"]) else "asset")
    return {
        "name": path.stem,
        "extension": suffix,
        "asset_type": asset_type,
        "asset_role": role,
        "path": str(path) if suffix not in FONT_EXTENSIONS else "",
        "file_size_bytes": size,
        "metadata_only": suffix in METADATA_ONLY_EXTENSIONS,
        "content_included": False,
        "execution_enabled": False,
    }


def _asset_roots(root: Path | None = None) -> list[Path]:
    if root is not None:
        return [root]
    roots = [ASSET_ROOT]
    if BRAND_ASSETS_ROOT.exists():
        roots.extend(path for path in sorted(BRAND_ASSETS_ROOT.glob("*/Assets")) if path.is_dir())
    return roots


def scan_assets(root: Path | None = None) -> dict[str, Any]:
    roots = _asset_roots(root)
    for asset_root in roots:
        initialize_asset_library(asset_root)
    assets = []
    for asset_root in roots:
        assets.extend(
            _asset_record(path)
            for path in sorted(asset_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS
        )
    return {
        "status": "ok",
        "root": str(roots[0]),
        "roots": [str(path) for path in roots],
        "assets": assets,
        "asset_count": len(assets),
        "metadata_only": True,
        "execution_enabled": False,
    }


def suggest_assets(package: dict[str, Any], limit: int = 5, root: Path | None = None) -> list[dict[str, Any]]:
    assets = scan_assets(root)["assets"]
    text = " ".join(str(package.get(key, "")) for key in ["brand_id", "niche", "style", "product_type", "title"]).lower()
    pride_query = any(token in text for token in ["pride", "lgbtq", "lgbt", "trans", "intersex", "rainbow"])
    scored = []
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        score = sum(1 for token in text.split() if token and token in name)
        if pride_query and any(token in name for token in ["pride", "lgbtq", "lgbt", "trans", "intersex", "rainbow", "flag"]):
            score += 10
        if "logo" in name:
            score += 2
        scored.append((score, asset))
    scored.sort(key=lambda item: (item[0], str(item[1].get("name", ""))), reverse=True)
    return [asset for score, asset in scored[:limit] if score > 0 or len(scored) <= limit]
