from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jamesos.config import VAULT


PACK_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Assets" / "Packs"

ASSET_CATEGORIES = {
    "flags",
    "hearts",
    "stars",
    "flowers",
    "bows",
    "sparkles",
    "animals",
    "seasonal",
    "typography_frames",
    "badges",
    "patterns",
    "backgrounds",
    "icons",
    "product_safe_patterns",
}

ASSET_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ttf", ".otf", ".ai", ".eps", ".pdf"}
FONT_EXTENSIONS = {".ttf", ".otf"}
METADATA_ONLY_EXTENSIONS = FONT_EXTENSIONS | {".ai", ".eps", ".pdf"}

SAFETY = {
    "provider_writes_enabled": False,
    "calls_printify": False,
    "calls_inkedjoy": False,
    "calls_etsy": False,
    "uploads": False,
    "publishes": False,
    "orders": False,
    "sends": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    return "_".join(part for part in normalized.split("_") if part) or "asset_pack"


def _category_for(path: Path, requested: str | None = None) -> str:
    if requested:
        category = _slug(requested)
        return category if category in ASSET_CATEGORIES else "icons"
    parts = {_slug(part) for part in path.parts}
    for category in ASSET_CATEGORIES:
        if category in parts:
            return category
    name = _slug(path.stem)
    checks = {
        "flags": ["flag", "pride"],
        "hearts": ["heart"],
        "stars": ["star"],
        "flowers": ["flower", "floral"],
        "bows": ["bow"],
        "sparkles": ["sparkle", "glitter"],
        "animals": ["cat", "dog", "animal"],
        "seasonal": ["halloween", "christmas", "valentine", "seasonal"],
        "typography_frames": ["frame", "typography"],
        "badges": ["badge"],
        "patterns": ["pattern", "repeat"],
        "backgrounds": ["background", "texture"],
        "product_safe_patterns": ["safe_pattern", "product_safe"],
    }
    for category, tokens in checks.items():
        if any(token in name for token in tokens):
            return category
    return "icons"


def _iter_source_files(source: Path, temp_dir: Path) -> list[Path]:
    if source.is_dir():
        return [path for path in sorted(source.rglob("*")) if path.is_file()]
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member.is_dir() or member_path.is_absolute() or ".." in member_path.parts:
                    continue
                archive.extract(member, temp_dir)
        return [path for path in sorted(temp_dir.rglob("*")) if path.is_file()]
    if source.is_file():
        return [source]
    raise FileNotFoundError(f"Asset pack source not found: {source}")


def _asset_record(source_file: Path, dest_file: Path, pack_folder: Path, license_metadata: dict[str, Any]) -> dict[str, Any]:
    suffix = dest_file.suffix.lower()
    relative = dest_file.relative_to(pack_folder)
    return {
        "name": dest_file.stem,
        "category": dest_file.parent.name,
        "extension": suffix,
        "asset_type": "font" if suffix in FONT_EXTENSIONS else suffix.lstrip("."),
        "relative_path": str(relative),
        "storage_path": "" if suffix in FONT_EXTENSIONS else str(dest_file),
        "metadata_only": suffix in METADATA_ONLY_EXTENSIONS,
        "content_included": False,
        "file_size_bytes": dest_file.stat().st_size if dest_file.exists() else 0,
        "original_name": source_file.name,
        "license": license_metadata,
    }


def import_asset_pack(
    source: str | Path,
    *,
    pack_name: str | None = None,
    category: str | None = None,
    license_metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    pack_root = root or PACK_ROOT
    pack_root.mkdir(parents=True, exist_ok=True)
    name = _slug(pack_name or source_path.stem)
    pack_folder = pack_root / name
    pack_folder.mkdir(parents=True, exist_ok=True)
    for item in ASSET_CATEGORIES:
        (pack_folder / item).mkdir(parents=True, exist_ok=True)

    license_record = {
        "source": "",
        "license": "",
        "commercial_allowed": False,
        "attribution_required": True,
        "notes": "",
        "imported_at": _now(),
        **(license_metadata or {}),
    }

    temp_dir = pack_folder / ".extract_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    try:
        for source_file in _iter_source_files(source_path, temp_dir):
            suffix = source_file.suffix.lower()
            if suffix not in ASSET_EXTENSIONS:
                continue
            asset_category = _category_for(source_file.relative_to(temp_dir) if temp_dir in source_file.parents else source_file, category)
            dest_dir = pack_folder / asset_category
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / source_file.name
            counter = 2
            while dest_file.exists():
                dest_file = dest_dir / f"{source_file.stem}_{counter}{source_file.suffix}"
                counter += 1
            shutil.copy2(source_file, dest_file)
            assets.append(_asset_record(source_file, dest_file, pack_folder, license_record))
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    manifest = {
        "status": "ok",
        "pack_name": name,
        "pack_folder": str(pack_folder),
        "asset_count": len(assets),
        "assets": assets,
        "license": license_record,
        "categories": sorted(ASSET_CATEGORIES),
        "font_files_metadata_only": True,
        "binary_contents_exposed": False,
        "safety": SAFETY,
    }
    (pack_folder / "asset_pack_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def list_asset_packs(*, root: Path | None = None) -> dict[str, Any]:
    pack_root = root or PACK_ROOT
    packs = []
    if pack_root.exists():
        for manifest_path in sorted(pack_root.glob("*/asset_pack_manifest.json")):
            try:
                packs.append(json.loads(manifest_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return {"status": "ok", "pack_count": len(packs), "packs": packs, "safety": SAFETY}
