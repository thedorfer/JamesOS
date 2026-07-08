from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from creative_intelligence.config import READONLY_SAFETY
from jamesos.config import VAULT


SALES_ROOT = VAULT / "JamesOS" / "CreativeIntelligence" / "EtsySales"
SALES_HISTORY_PATH = SALES_ROOT / "sales_history.jsonl"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Etsy Sales Intelligence.md"

FIELDS = [
    "pod_provider",
    "fulfillment_source",
    "production_partner",
    "product_type",
    "inferred_product_type",
    "design_family",
    "recipe_id",
    "revenue",
    "quantity_sold",
    "conversion_rate",
    "favorite_rate",
    "repeat_buyer_signal",
    "seasonality_signal",
]

SAFETY = {
    **READONLY_SAFETY,
    "etsy_write_api_enabled": False,
    "printify_enabled": False,
    "inkedjoy_enabled": False,
    "provider_writes_enabled": False,
    "uploads_enabled": False,
    "publishing_enabled": False,
    "orders_enabled": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()
        try:
            return float(cleaned) / 100.0
        except ValueError:
            return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _quantity(value: Any) -> int:
    return max(0, int(round(_number(value))))


def _infer_product_type(row: dict[str, Any]) -> str:
    explicit = _text(row.get("inferred_product_type") or row.get("product_type"))
    if explicit:
        return explicit.lower().replace(" ", "_")
    title = " ".join(_text(row.get(key)).lower() for key in ["title", "listing_title", "item_name", "name"])
    checks = {
        "womens_underwear": ["underwear", "panty", "panties", "thong"],
        "t_shirt": ["t-shirt", "tee", "shirt"],
        "hoodie": ["hoodie", "sweatshirt"],
        "mug": ["mug", "cup"],
        "sticker": ["sticker", "decal"],
        "tote_bag": ["tote", "bag"],
        "poster": ["poster", "print", "wall art"],
    }
    for product_type, tokens in checks.items():
        if any(token in title for token in tokens):
            return product_type
    return ""


def _seasonality(row: dict[str, Any]) -> str:
    explicit = _text(row.get("seasonality_signal") or row.get("season") or row.get("holiday"))
    if explicit:
        return explicit.lower()
    text = " ".join(_text(row.get(key)).lower() for key in ["title", "listing_title", "tags", "niche"])
    for token in ["halloween", "christmas", "valentine", "pride", "back to school", "mother's day", "father's day"]:
        if token in text:
            return token
    return ""


def normalize_sales_row(row: dict[str, Any], *, source: str = "import") -> dict[str, Any]:
    """Normalize one Etsy sales row without assuming which POD provider fulfilled it."""
    revenue = _number(row.get("revenue") or row.get("total") or row.get("amount") or row.get("order_value"))
    quantity = _quantity(row.get("quantity_sold") or row.get("quantity") or row.get("qty") or row.get("orders"))
    views = _number(row.get("views"))
    favorites = _number(row.get("favorites") or row.get("favourites"))
    conversion_rate = _number(row.get("conversion_rate"))
    favorite_rate = _number(row.get("favorite_rate"))
    if not conversion_rate and views:
        conversion_rate = quantity / views
    if not favorite_rate and views:
        favorite_rate = favorites / views

    normalized = {
        "source": source,
        "source_row_id": _text(row.get("source_row_id") or row.get("transaction_id") or row.get("order_id") or row.get("receipt_id") or row.get("listing_id")),
        "title": _text(row.get("title") or row.get("listing_title") or row.get("item_name") or row.get("name")),
        "niche": _text(row.get("niche") or row.get("audience") or row.get("market")),
        "motifs": [_text(item).lower() for item in row.get("motifs", [])] if isinstance(row.get("motifs"), list) else [_text(row.get("motif")).lower()] if row.get("motif") else [],
        "color_palette": [_text(item).lower() for item in row.get("color_palette", [])] if isinstance(row.get("color_palette"), list) else [_text(row.get("palette") or row.get("color")).lower()] if (row.get("palette") or row.get("color")) else [],
        "pod_provider": _text(row.get("pod_provider") or row.get("provider")).lower(),
        "fulfillment_source": _text(row.get("fulfillment_source") or row.get("fulfillment")).lower(),
        "production_partner": _text(row.get("production_partner") or row.get("partner")),
        "product_type": _text(row.get("product_type")).lower().replace(" ", "_"),
        "inferred_product_type": _infer_product_type(row),
        "design_family": _text(row.get("design_family")).lower(),
        "recipe_id": _text(row.get("recipe_id")),
        "revenue": round(revenue, 2),
        "quantity_sold": quantity,
        "conversion_rate": round(conversion_rate, 4),
        "favorite_rate": round(favorite_rate, 4),
        "repeat_buyer_signal": bool(row.get("repeat_buyer_signal") or row.get("repeat_buyer") or row.get("is_repeat_buyer")),
        "seasonality_signal": _seasonality(row),
        "imported_at": _now(),
        "raw_metadata": {key: value for key, value in row.items() if key not in FIELDS and key not in {"motifs", "color_palette"}},
    }
    return normalized


def import_sales_rows(
    rows: Iterable[dict[str, Any]],
    *,
    source: str = "etsy_csv",
    root: Path | None = None,
) -> dict[str, Any]:
    sales_root = root or SALES_ROOT
    sales_root.mkdir(parents=True, exist_ok=True)
    path = sales_root / "sales_history.jsonl"
    normalized = [normalize_sales_row(row, source=source) for row in rows]
    with path.open("a", encoding="utf-8") as handle:
        for item in normalized:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    return {"status": "ok", "imported": len(normalized), "path": str(path), "safety": SAFETY}


def import_sales_csv(csv_path: str | Path, *, source: str = "etsy_csv", root: Path | None = None) -> dict[str, Any]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return import_sales_rows(rows, source=source, root=root)


def list_sales_history(*, limit: int = 500, root: Path | None = None) -> list[dict[str, Any]]:
    sales_root = root or SALES_ROOT
    path = sales_root / "sales_history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-max(1, min(int(limit), 5000)):]


def _tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        raw = " ".join(_text(item) for item in value)
    else:
        raw = _text(value)
    return {token for token in raw.lower().replace("_", " ").replace("-", " ").split() if token}


def sales_signal_for_candidate(candidate: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    rows = list_sales_history(root=root)
    if not rows:
        return {"boost": 0.0, "matched_rows": 0, "matched_fields": [], "provider_notes": "No imported Etsy sales history.", "safety": SAFETY}

    candidate_fields = {
        "design_family": _tokens(candidate.get("design_family") or (candidate.get("design_recipe") or {}).get("design_family")),
        "product_type": _tokens(candidate.get("product_type") or (candidate.get("design_recipe") or {}).get("product_type")),
        "niche": _tokens(candidate.get("niche") or candidate.get("audience")),
        "motif": _tokens(candidate.get("motif") or candidate.get("motifs") or (candidate.get("design_recipe") or {}).get("motifs")),
        "color_palette": _tokens(candidate.get("color_palette") or candidate.get("palette") or (candidate.get("design_recipe") or {}).get("palette")),
        "seasonality": _tokens(candidate.get("seasonality_signal") or candidate.get("season") or candidate.get("niche")),
        "recipe_id": {_text(candidate.get("recipe_id") or (candidate.get("design_recipe") or {}).get("recipe_id")).lower()},
    }
    matched_fields: set[str] = set()
    strength = 0.0
    matched_rows = 0
    provider_examples: set[str] = set()
    for row in rows:
        row_fields = {
            "design_family": _tokens(row.get("design_family")),
            "product_type": _tokens(row.get("product_type") or row.get("inferred_product_type")),
            "niche": _tokens(row.get("niche") or row.get("title")),
            "motif": _tokens(row.get("motifs")),
            "color_palette": _tokens(row.get("color_palette")),
            "seasonality": _tokens(row.get("seasonality_signal")),
            "recipe_id": {_text(row.get("recipe_id")).lower()},
        }
        row_matches = [field for field, tokens in candidate_fields.items() if tokens and "" not in tokens and tokens & row_fields[field]]
        if not row_matches:
            continue
        matched_rows += 1
        matched_fields.update(row_matches)
        revenue = float(row.get("revenue") or 0)
        quantity = int(row.get("quantity_sold") or 0)
        conversion = float(row.get("conversion_rate") or 0)
        favorite = float(row.get("favorite_rate") or 0)
        strength += min(0.10, revenue / 1000.0)
        strength += min(0.08, quantity * 0.015)
        strength += min(0.06, conversion * 2)
        strength += min(0.04, favorite)
        if row.get("repeat_buyer_signal"):
            strength += 0.03
        if row.get("pod_provider"):
            provider_examples.add(str(row["pod_provider"]))

    boost = round(max(0.0, min(0.25, strength)), 3)
    return {
        "boost": boost,
        "matched_rows": matched_rows,
        "matched_fields": sorted(matched_fields),
        "provider_notes": "Providers are retained as fulfillment context, not treated as design success.",
        "providers_seen": sorted(provider_examples),
        "safety": SAFETY,
    }


def summarize_sales_history(*, root: Path | None = None) -> dict[str, Any]:
    rows = list_sales_history(root=root)
    totals = {
        "rows": len(rows),
        "revenue": round(sum(float(row.get("revenue") or 0) for row in rows), 2),
        "quantity_sold": sum(int(row.get("quantity_sold") or 0) for row in rows),
    }
    by_provider: dict[str, int] = {}
    by_design_family: dict[str, float] = {}
    by_product_type: dict[str, int] = {}
    for row in rows:
        provider = str(row.get("pod_provider") or "unknown")
        family = str(row.get("design_family") or "unknown")
        product_type = str(row.get("product_type") or row.get("inferred_product_type") or "unknown")
        by_provider[provider] = by_provider.get(provider, 0) + 1
        by_design_family[family] = round(by_design_family.get(family, 0.0) + float(row.get("revenue") or 0), 2)
        by_product_type[product_type] = by_product_type.get(product_type, 0) + int(row.get("quantity_sold") or 0)
    return {
        "status": "ok" if rows else "empty",
        "totals": totals,
        "by_provider": by_provider,
        "by_design_family_revenue": by_design_family,
        "by_product_type_quantity": by_product_type,
        "safety": SAFETY,
    }


def write_sales_intelligence_report(*, root: Path | None = None, report_path: Path | None = None) -> dict[str, Any]:
    summary = summarize_sales_history(root=root)
    out = report_path or REPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Etsy Sales Intelligence",
        "",
        "Read-only imported sales history for provider-agnostic creative learning.",
        "",
        "## Safety",
        "",
        "- Etsy writes: disabled",
        "- POD provider writes: disabled",
        "- Upload, publish, order, send: disabled",
        "",
        "## Totals",
        "",
    ]
    totals = summary["totals"]
    lines.extend([
        f"- Rows: {totals['rows']}",
        f"- Revenue: {totals['revenue']}",
        f"- Quantity sold: {totals['quantity_sold']}",
        "",
        "## Providers Seen",
        "",
    ])
    providers = summary["by_provider"] or {"none": 0}
    lines.extend(f"- {provider}: {count}" for provider, count in sorted(providers.items()))
    lines.extend(["", "## Design Family Revenue", ""])
    families = summary["by_design_family_revenue"] or {"none": 0}
    lines.extend(f"- {family}: {revenue}" for family, revenue in sorted(families.items(), key=lambda item: item[1], reverse=True))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "report_path": str(out), "summary": summary, "safety": SAFETY}
