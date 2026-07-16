from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT
from jamesos.services.brand_registry import get_brand
from jamesos.services.creative_studio import create_pipeline
from jamesos.services.planner import create_plan
from creative_intelligence.services.compatibility_service import assess_compatibility, select_compatible_package


PROFILE_ROOT = VAULT / "JamesOS" / "Profiles"
DEFAULT_PROFILE_ID = "commerce_shop"


def _profile_id() -> str:
    pointer = PROFILE_ROOT / "selected_commerce_profile"
    return pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else DEFAULT_PROFILE_ID


def _profile_root() -> Path:
    return PROFILE_ROOT / _profile_id()


CONFIG_PATH = _profile_root() / "product_pipeline.yaml"
DRAFTS_ROOT = _profile_root() / "Drafts"
REPORT_PATH = _profile_root() / "Reports" / "Product Drafts.md"
BRAND_ID = DEFAULT_PROFILE_ID

ROTATING_OPTIONS = ["shirt", "sweatshirt", "hoodie", "tote", "mug", "seasonal_accessory"]
INTIMATE_POD_PRODUCT_TERMS = {"womens_underwear", "panties", "panty", "thong", "thongs"}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "daily_products": [
        {"type": "womens_underwear", "count": 1, "required": True},
        {
            "type": "rotating",
            "count": 1,
            "options": ROTATING_OPTIONS,
        },
    ],
    "niches": [
        "LGBTQ+ pride",
        "trans pride",
        "nonbinary pride",
        "ally/supporter",
        "inclusive teacher",
        "self-love and confidence",
        "mental health positivity",
        "be yourself affirmation",
        "mom pride / family pride",
        "Thai/English identity",
        "custom pronoun/name",
        "holiday pride",
        "seasonal inclusive",
        "Valentines love-is-love",
        "Pride Month",
    ],
    "safety": {
        "create_printify_draft": False,
        "publish_to_etsy": False,
        "send_to_production": False,
        "require_james_approval": True,
    },
    "image_generation": {
        "provider": "comfyui",
        "enabled": False,
        "execution_enabled": False,
    },
}


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_string() -> str:
    return date.today().isoformat()


def initialize_config() -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
        created = True
    DRAFTS_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "created": created, "config_path": str(CONFIG_PATH)}


def load_config() -> dict[str, Any]:
    initialize_config()
    try:
        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    merged = {**DEFAULT_CONFIG, **loaded}
    merged["safety"] = {**DEFAULT_CONFIG["safety"], **(loaded.get("safety") or {})}
    merged["image_generation"] = {
        **DEFAULT_CONFIG["image_generation"],
        **(loaded.get("image_generation") or {}),
    }
    return merged


def _date_index(run_date: str) -> int:
    try:
        return date.fromisoformat(run_date).toordinal()
    except ValueError:
        return date.today().toordinal()


def _rotating_product(config: dict[str, Any], run_date: str) -> str:
    options = list(ROTATING_OPTIONS)
    for item in config.get("daily_products", []):
        if item.get("type") == "rotating" and item.get("options"):
            options = [str(option) for option in item["options"]]
            break
    if not options:
        options = list(ROTATING_OPTIONS)
    return options[_date_index(run_date) % len(options)]


def _niche(config: dict[str, Any], run_date: str, index: int) -> str:
    niches = [str(item) for item in config.get("niches", [])] or list(DEFAULT_CONFIG["niches"])
    return niches[(_date_index(run_date) + index) % len(niches)]


def _niches(config: dict[str, Any]) -> list[str]:
    return [str(item) for item in config.get("niches", [])] or list(DEFAULT_CONFIG["niches"])


def _compatible_package(config: dict[str, Any], product_type: str, run_date: str, index: int) -> dict[str, Any]:
    return select_compatible_package(
        product_type,
        _niches(config),
        start_index=_date_index(run_date) + index,
        brand_id=BRAND_ID,
    )


def _product_label(product_type: str) -> str:
    return product_type.replace("_", " ").title()


def _pod_provider_for_product(product_type: str, brand: dict[str, Any]) -> str:
    normalized = product_type.strip().lower()
    rules = brand.get("provider_rules") or {}
    rule = rules.get(normalized) if isinstance(rules, dict) else None
    if isinstance(rule, dict) and rule.get("preferred_provider"):
        return str(rule["preferred_provider"])
    if normalized in INTIMATE_POD_PRODUCT_TERMS:
        return "printify"
    return str(brand.get("preferred_pod_provider") or brand.get("fallback_pod_provider") or "printify")


def _draft(product_type: str, niche: str, run_date: str, index: int) -> dict[str, Any]:
    label = _product_label(product_type)
    brand = get_brand(BRAND_ID)
    pod_provider = _pod_provider_for_product(product_type, brand)
    compatibility = assess_compatibility(product_type, niche, brand_id=BRAND_ID)
    if not compatibility["compatible"]:
        raise ValueError(compatibility["compatibility_reason"])
    concept = f"{label} with an inclusive {niche} affirmation design"
    title = f"{label} - {niche} Affirmation"
    tags = [
        "pride apparel",
        "inclusive gift",
        niche.lower().replace("/", " "),
        product_type.replace("_", " "),
        "commerce_shop",
        "sample",
        "affirmation",
        "needs review",
    ][:13]
    return {
        "date": run_date,
        "brand_id": brand["brand_id"],
        "brand_name": brand["display_name"],
        "brand_voice": brand.get("brand_voice", ""),
        "product_type": product_type,
        "pod_provider": pod_provider,
        "provider_status": "needs_design",
        "niche": niche,
        "product_idea": concept,
        "design_prompt": (
            f"Draft-only flat printable design artwork concept for {label}: standalone centered print graphic, "
            f"clean inclusive typography, warm confident tone, {niche} theme, POD-safe print-ready composition, "
            "white or transparent-background-friendly background, no person, no model, no mockup, no copyrighted logos."
        ),
        "negative_prompt": (
            "No copyrighted characters, no hateful symbols, no medical claims, no live marketplace upload, "
            "no photorealistic people, no person, no human model, no wearing, no product photo, no lifestyle photo, "
            "no room, no mannequin, no hands, no body, no portrait, no mockup, no explicit content."
        ),
        "title": title,
        "etsy_tags": tags,
        "etsy_description": (
            f"Draft listing copy for a {label.lower()} concept celebrating {niche}. "
            "This is a local review draft and is not a live Etsy listing."
        ),
        "pricing_notes": "Draft pricing only. Review product cost, shipping, fees, and margin before approval.",
        "printify_blueprint_search_terms": [label.lower(), product_type.replace("_", " "), "print on demand"],
        "printify_notes": "No Printify API call made. Search terms are for future manual or approved draft setup only when provider is Printify.",
        "pod_notes": f"No {pod_provider} API call made. Local draft is for provider review only.",
        "status": "needs_review",
        "brand_compatibility_status": compatibility.get("brand_compatibility_status", compatibility["compatibility_status"]),
        "brand_compatibility_reason": compatibility.get("brand_compatibility_reason", compatibility["compatibility_reason"]),
        "compatibility_status": compatibility["compatibility_status"],
        "compatibility_reason": compatibility["compatibility_reason"],
        "blocked_terms": compatibility["blocked_terms"],
        "approval_required": True,
        "external_execution_enabled": False,
        "comfyui_execution_enabled": False,
        "printify_execution_enabled": False,
        "etsy_execution_enabled": False,
        "publish_enabled": False,
        "order_enabled": False,
        "send_enabled": False,
        "draft_number": index + 1,
    }


def _draft_product_types(config: dict[str, Any], run_date: str) -> list[str]:
    product_types: list[str] = []
    for item in config.get("daily_products", []):
        count = int(item.get("count", 1) or 1)
        item_type = str(item.get("type", "")).strip()
        if item_type == "womens_underwear":
            product_types.extend(["womens_underwear"] * count)
        elif item_type == "rotating":
            product_types.extend([_rotating_product(config, run_date)] * count)
    if not product_types:
        product_types = ["womens_underwear", _rotating_product(config, run_date)]
    return product_types[:2]


def _write_drafts(run_date: str, drafts: list[dict[str, Any]]) -> list[str]:
    folder = DRAFTS_ROOT / run_date
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, draft in enumerate(drafts, start=1):
        product_type = draft["product_type"]
        path = folder / f"{index:02d}-{product_type}.json"
        path.write_text(json.dumps(draft, indent=2, sort_keys=True), encoding="utf-8")
        paths.append(str(path))
    return paths


def generate_daily_product_drafts(run_date: str | None = None) -> dict[str, Any]:
    config = load_config()
    selected_date = run_date or today_string()
    product_types = _draft_product_types(config, selected_date)
    drafts = []
    for index, product_type in enumerate(product_types):
        package = _compatible_package(config, product_type, selected_date, index)
        drafts.append(_draft(package["product_type"], package["niche"], selected_date, index))
    if len(drafts) != 2:
        raise ValueError("Commerce Shop daily generation must produce exactly 2 drafts")

    planner_result = create_plan(
        "daily_product_generation",
        "Generate today's Commerce Shop product drafts",
        {"date": selected_date, "draft_count": len(drafts)},
    )
    draft_paths = _write_drafts(selected_date, drafts)
    pipeline_job = create_pipeline({
        "title": f"Commerce Shop daily product drafts {selected_date}",
        "brand_id": BRAND_ID,
        "product_line": "Commerce Shop",
        "draft_count": len(drafts),
        "draft_paths": draft_paths,
        "planner": planner_result,
        "external_execution_enabled": False,
    })
    write_report()
    return {
        "status": "ok",
        "date": selected_date,
        "draft_count": len(drafts),
        "drafts": drafts,
        "draft_paths": draft_paths,
        "creative_pipeline_job": pipeline_job,
        "planner": planner_result,
        "safety": safety_status(config),
    }


def drafts_for_date(run_date: str) -> dict[str, Any]:
    folder = DRAFTS_ROOT / run_date
    drafts = []
    if folder.exists():
        for path in sorted(folder.glob("*.json")):
            drafts.append(json.loads(path.read_text(encoding="utf-8")))
    return {"status": "ok", "date": run_date, "drafts": drafts, "draft_count": len(drafts)}


def list_drafts(status: str | None = None) -> dict[str, Any]:
    DRAFTS_ROOT.mkdir(parents=True, exist_ok=True)
    drafts = []
    for path in sorted(DRAFTS_ROOT.glob("*/*.json"), reverse=True):
        item = json.loads(path.read_text(encoding="utf-8"))
        if status and item.get("status") != status:
            continue
        item["path"] = str(path)
        drafts.append(item)
    return {"status": "ok", "drafts": drafts, "draft_count": len(drafts)}


def safety_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    safety = cfg.get("safety", {})
    image = cfg.get("image_generation", {})
    return {
        "draft_only": True,
        "approval_required": bool(safety.get("require_james_approval", True)),
        "external_execution_enabled": False,
        "comfyui_execution_enabled": False,
        "image_generation_enabled": bool(image.get("enabled", False)),
        "image_generation_execution_enabled": False,
        "create_printify_draft": False,
        "publish_to_etsy": False,
        "send_to_production": False,
        "publish_enabled": False,
        "order_enabled": False,
        "send_enabled": False,
    }


def health() -> dict[str, Any]:
    cfg = load_config()
    return {
        "status": "ok",
        "name": "Commerce Shop Product Pipeline",
        "enabled": bool(cfg.get("enabled", True)),
        "draft_root": str(DRAFTS_ROOT),
        "report": str(REPORT_PATH),
        "daily_product_count": 2,
        "required_product": "womens_underwear",
        "rotating_options": ROTATING_OPTIONS,
        "safety": safety_status(cfg),
    }


def pipeline_status() -> dict[str, Any]:
    return health()


def write_report() -> dict[str, Any]:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    drafts = list_drafts().get("drafts", [])
    needs_review = [draft for draft in drafts if draft.get("status") == "needs_review"]
    lines = [
        "# Commerce Shop Product Drafts",
        "",
        f"Updated: {now_timestamp()}",
        "",
        "## Safety",
        "",
        "- Draft-only local product packages.",
        "- No ComfyUI execution.",
        "- No Printify API calls.",
        "- No Etsy API calls.",
        "- No publishing, ordering, or sending.",
        "- James approval is required before any future external action.",
        "",
        "## Needs Review",
        "",
    ]
    if not needs_review:
        lines.append("- None")
    for draft in needs_review[:50]:
        lines.append(
            f"- {draft.get('date')} - {draft.get('product_type')} - "
            f"{draft.get('niche')} - {draft.get('title')}"
        )
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report": str(REPORT_PATH), "needs_review": len(needs_review)}
