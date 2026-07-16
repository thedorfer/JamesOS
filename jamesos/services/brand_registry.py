from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


REGISTRY_PATH = VAULT / "JamesOS" / "Brands" / "brand_registry.yaml"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Brand Registry.md"

TEACHER_CHILD_TERMS = [
    "teacher",
    "school",
    "school staff",
    "classroom",
    "education",
    "gcu",
    "kids",
    "student",
    "back-to-school",
    "back to school",
    "special education",
    "speech therapy",
    "occupational therapy",
    "child",
    "children",
    "child-related",
]

INTIMATE_PRODUCT_TERMS = [
    "womens_underwear",
    "women's underwear",
    "underwear",
    "panties",
    "panty",
    "thong",
    "thongs",
    "lingerie",
    "intimate apparel",
    "intimates",
]

DEFAULT_REGISTRY: dict[str, Any] = {
    "brands": {
        "commerce_shop": {
            "brand_id": "commerce_shop",
            "display_name": "Commerce Shop",
            "shop_type": "Etsy/Printify apparel and gifts",
            "etsy_shop_name": "Commerce Shop",
            "printify_shop_id": "",
            "preferred_pod_provider": "printify",
            "fallback_pod_provider": "inkedjoy_manual_future",
            "provider_rules": {
                "womens_underwear": {"preferred_provider": "printify"},
                "panties": {"preferred_provider": "printify"},
                "panty": {"preferred_provider": "printify"},
                "thong": {"preferred_provider": "printify"},
                "thongs": {"preferred_provider": "printify"},
            },
            "status": "foundation",
            "enabled": True,
            "default": True,
            "brand_voice": "warm, inclusive, affirming, clever, and giftable",
            "target_audiences": [
                "LGBTQ+ community",
                "allies",
                "teachers and school staff",
                "moms and families",
                "Thai/English families",
                "massage therapists",
                "programmer spouses and families",
                "Katy/Texas locals",
            ],
            "allowed_niches": [
                "LGBTQ+ pride",
                "trans pride",
                "nonbinary pride",
                "ally/supporter",
                "self-love",
                "body positivity",
                "mental health positivity",
                "Thai/English identity",
                "holiday pride",
                "seasonal inclusive",
                "teacher shirts/gifts",
                "massage therapist humor",
                "mom life",
                "Texas/Katy local",
                "programmer spouse/family humor",
            ],
            "blocked_niches": [],
            "allowed_product_types": [
                "womens_underwear",
                "shirts",
                "shirt",
                "sweatshirts",
                "sweatshirt",
                "hoodies",
                "hoodie",
                "totes",
                "tote",
                "mugs",
                "mug",
                "stickers",
                "sticker",
                "seasonal_accessory",
            ],
            "blocked_product_types": [],
            "blocked_product_niche_pairs": [
                {
                    "product_terms": INTIMATE_PRODUCT_TERMS,
                    "niche_terms": TEACHER_CHILD_TERMS,
                    "reason": "Teacher, school, classroom, education, GCU, kids, student, back-to-school, special education, speech therapy, occupational therapy, and child-related niches must not pair with women's underwear, panties, thongs, lingerie, or intimate apparel.",
                }
            ],
            "preferred_product_mix": [
                {"type": "womens_underwear", "count": 1, "required": True},
                {"type": "rotating", "count": 1, "options": ["shirt", "sweatshirt", "hoodie", "tote", "mug", "seasonal_accessory"]},
            ],
            "colors": ["rainbow", "trans pride palette", "warm neutrals", "pink", "teal", "cream"],
            "fonts": ["bold readable sans", "friendly script accents"],
            "design_styles": ["inclusive typography", "clean giftable graphics", "warm affirmation"],
            "seo_preferences": ["pride gift", "inclusive apparel", "affirmation gift", "teacher gift"],
            "pricing_rules": {"approval_required": True, "notes": "Review costs, fees, shipping, and margin before external action."},
            "mockup_preferences": {"approval_required": True, "style": "clean product-forward mockups"},
            "trademark_safety_notes": "Avoid copyrighted logos, team names, brand names, celebrity names, and protected slogans.",
            "approval_rules": {
                "require_approval_for_all_external_actions": True,
                "writes_enabled": False,
                "publishing_enabled": False,
                "upload_enabled": False,
                "order_enabled": False,
                "send_enabled": False,
            },
            "integrations": {
                "etsy": {"enabled": False, "readonly": True, "shop_id": "", "shop_name": "Commerce Shop", "writes_enabled": False},
                "printify": {"enabled": True, "readonly": True, "shop_id": "", "writes_enabled": False, "draft_creation_enabled": False, "order_enabled": False},
                "comfyui": {"enabled": False, "execution_enabled": False},
            },
        },
        "bagholder_supply_co": {
            "brand_id": "bagholder_supply_co",
            "display_name": "Bagholder Supply Co",
            "shop_type": "Etsy/Printify market-chaos apparel shop",
            "etsy_shop_name": "Bagholder Supply Co",
            "printify_shop_id": "",
            "preferred_pod_provider": "printify",
            "fallback_pod_provider": "",
            "provider_rules": {},
            "niche": "market_chaos_degen_tshirts",
            "product_focus": ["shirts"],
            "daily_design_target": {"min": 3, "max": 5},
            "stage_default": "print_design_basic",
            "status": "foundation",
            "enabled": True,
            "default": False,
            "brand_voice": "sharp, funny, finance-meme native, market-chaos aware, clean enough for marketplace review",
            "target_audiences": ["traders", "finance meme fans", "internet culture people", "market chaos humor buyers"],
            "allowed_niches": ["market chaos", "degen humor", "finance memes", "trading jokes", "bagholder humor"],
            "blocked_niches": [],
            "allowed_product_types": ["shirts", "shirt"],
            "blocked_product_types": INTIMATE_PRODUCT_TERMS,
            "blocked_product_niche_pairs": [],
            "preferred_product_mix": [{"type": "shirt", "count": 3, "required": True}],
            "colors": ["black", "white", "green", "red", "neon accent"],
            "fonts": ["bold condensed sans", "meme caption style"],
            "design_styles": ["bold typography", "finance meme typography", "flat print design"],
            "seo_preferences": ["trader shirt", "finance meme shirt", "degen shirt", "market chaos shirt"],
            "pricing_rules": {"approval_required": True},
            "mockup_preferences": {"approval_required": True, "style": "simple apparel mockups only after design approval"},
            "trademark_safety_notes": "Avoid exchange logos, ticker misuse, financial advice claims, celebrity names, and protected memes.",
            "approval_rules": {
                "require_approval_for_all_external_actions": True,
                "writes_enabled": False,
                "publishing_enabled": False,
                "upload_enabled": False,
                "order_enabled": False,
                "send_enabled": False,
            },
            "integrations": {
                "etsy": {"enabled": False, "readonly": True, "shop_id": "", "shop_name": "Bagholder Supply Co", "writes_enabled": False},
                "printify": {"enabled": True, "readonly": True, "shop_id": "", "writes_enabled": False, "draft_creation_enabled": False, "order_enabled": False},
                "comfyui": {"enabled": False, "execution_enabled": False},
            },
        },
        "cheeky_peach_prints": {
            "brand_id": "cheeky_peach_prints",
            "display_name": "Cheeky Peach Prints",
            "shop_type": "Etsy/Printify playful seasonal underwear shop",
            "etsy_shop_name": "Cheeky Peach Prints",
            "printify_shop_id": "",
            "preferred_pod_provider": "printify",
            "fallback_pod_provider": "inkedjoy_manual_future",
            "provider_rules": {
                "womens_underwear": {"preferred_provider": "printify"},
                "panties": {"preferred_provider": "printify"},
                "panty": {"preferred_provider": "printify"},
                "thong": {"preferred_provider": "printify"},
                "thongs": {"preferred_provider": "printify"},
            },
            "niche": "womens_underwear_playful_seasonal",
            "product_focus": ["womens_underwear", "panties", "thong"],
            "daily_design_target": {"min": 3, "max": 5},
            "stage_default": "print_design_basic",
            "status": "foundation",
            "enabled": True,
            "default": False,
            "brand_voice": "playful, cheeky, seasonal, upbeat, clean non-explicit humor",
            "target_audiences": ["adult gift shoppers", "seasonal apparel buyers", "playful underwear customers"],
            "allowed_niches": ["self-love", "body positivity", "holiday playful", "seasonal inclusive", "Valentines love-is-love", "clean adult spouse/partner humor"],
            "blocked_niches": TEACHER_CHILD_TERMS,
            "allowed_product_types": ["womens_underwear", "panties", "panty", "thong", "thongs"],
            "blocked_product_types": [],
            "blocked_product_niche_pairs": [
                {
                    "product_terms": INTIMATE_PRODUCT_TERMS,
                    "niche_terms": TEACHER_CHILD_TERMS,
                    "reason": "Teacher, school, classroom, education, GCU, kids, student, back-to-school, special education, speech therapy, occupational therapy, and child-related niches must not pair with women's underwear, panties, thongs, lingerie, or intimate apparel.",
                }
            ],
            "preferred_product_mix": [{"type": "womens_underwear", "count": 3, "required": True}],
            "colors": ["peach", "pink", "cream", "red", "white", "seasonal accent"],
            "fonts": ["bold readable sans", "playful script accents"],
            "design_styles": ["flat print design", "seasonal typography", "cute playful graphics"],
            "seo_preferences": ["playful underwear", "seasonal underwear", "funny adult gift", "Valentines underwear"],
            "pricing_rules": {"approval_required": True},
            "mockup_preferences": {"approval_required": True, "style": "clean product-forward mockups only after design approval"},
            "trademark_safety_notes": "Avoid copyrighted characters, brand names, celebrity names, and protected slogans.",
            "approval_rules": {
                "require_approval_for_all_external_actions": True,
                "writes_enabled": False,
                "publishing_enabled": False,
                "upload_enabled": False,
                "order_enabled": False,
                "send_enabled": False,
            },
            "integrations": {
                "etsy": {"enabled": False, "readonly": True, "shop_id": "", "shop_name": "Cheeky Peach Prints", "writes_enabled": False},
                "printify": {"enabled": True, "readonly": True, "shop_id": "", "writes_enabled": False, "draft_creation_enabled": False, "order_enabled": False},
                "comfyui": {"enabled": False, "execution_enabled": False},
            },
        },
        "degen_market_chaos": {
            "brand_id": "degen_market_chaos",
            "display_name": "Degen Market Chaos",
            "shop_type": "Etsy/Printify meme apparel and gifts placeholder",
            "etsy_shop_name": "",
            "printify_shop_id": "",
            "preferred_pod_provider": "printify",
            "fallback_pod_provider": "",
            "provider_rules": {},
            "status": "placeholder",
            "enabled": False,
            "default": False,
            "brand_voice": "fast, funny, internet-native, finance-meme aware, clean enough for marketplace review",
            "target_audiences": ["traders", "finance meme fans", "internet culture people"],
            "allowed_niches": ["market chaos", "internet culture", "degen humor", "finance memes", "trading jokes"],
            "blocked_niches": [],
            "allowed_product_types": ["shirts", "shirt", "hoodies", "hoodie", "mugs", "mug", "stickers", "sticker", "hats", "hat"],
            "blocked_product_types": INTIMATE_PRODUCT_TERMS,
            "blocked_product_niche_pairs": [],
            "preferred_product_mix": [{"type": "rotating", "count": 1, "options": ["shirt", "hoodie", "mug", "sticker", "hat"]}],
            "colors": ["black", "green", "red", "white", "neon accent"],
            "fonts": ["bold condensed sans", "meme caption style"],
            "design_styles": ["finance meme typography", "market chaos jokes", "clean non-explicit humor"],
            "seo_preferences": ["finance meme", "trader gift", "degen humor"],
            "pricing_rules": {"approval_required": True},
            "mockup_preferences": {"approval_required": True, "style": "simple apparel and mug mockups"},
            "trademark_safety_notes": "Avoid exchange logos, ticker misuse, financial advice claims, celebrity names, and protected memes.",
            "approval_rules": {
                "require_approval_for_all_external_actions": True,
                "writes_enabled": False,
                "publishing_enabled": False,
                "upload_enabled": False,
                "order_enabled": False,
                "send_enabled": False,
            },
            "integrations": {
                "etsy": {"enabled": False, "readonly": True, "shop_id": "", "shop_name": "", "writes_enabled": False},
                "printify": {"enabled": False, "shop_id": "", "writes_enabled": False},
                "comfyui": {"enabled": False, "execution_enabled": False},
            },
        },
    }
}


PRINTIFY_INTIMATE_PROVIDER_RULES = {
    "womens_underwear": {"preferred_provider": "printify"},
    "panties": {"preferred_provider": "printify"},
    "panty": {"preferred_provider": "printify"},
    "thong": {"preferred_provider": "printify"},
    "thongs": {"preferred_provider": "printify"},
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _norm(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").lower().strip()


def _contains_any(value: str, terms: list[str]) -> list[str]:
    normalized = _norm(value)
    matches = []
    for term in terms:
        term_norm = _norm(str(term))
        if term_norm and term_norm in normalized:
            matches.append(str(term))
    return matches


def _apply_current_provider_defaults(brand_id: str, brand: dict[str, Any]) -> dict[str, Any]:
    """Keep current MVP provider decision stable even if older YAML has InkedJoy defaults."""
    if brand_id in {"commerce_shop", "cheeky_peach_prints"}:
        brand["preferred_pod_provider"] = "printify"
        brand["fallback_pod_provider"] = "inkedjoy_manual_future"
        brand["provider_rules"] = {**(brand.get("provider_rules") or {}), **PRINTIFY_INTIMATE_PROVIDER_RULES}
    if brand_id == "bagholder_supply_co":
        brand["preferred_pod_provider"] = "printify"
        brand["fallback_pod_provider"] = ""
    printify = (brand.get("integrations") or {}).get("printify")
    if isinstance(printify, dict):
        printify["writes_enabled"] = False
        printify["draft_creation_enabled"] = False
        printify["order_enabled"] = False
    return brand


def initialize_brand_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not registry_path.exists():
        registry_path.write_text(yaml.safe_dump(DEFAULT_REGISTRY, sort_keys=False), encoding="utf-8")
        created = True
    return {"status": "ok", "created": created, "registry_path": str(registry_path)}


def load_brand_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    initialize_brand_registry(registry_path)
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    loaded_brands = loaded.get("brands") or {}
    brands: dict[str, Any] = {}
    for brand_id, default_brand in DEFAULT_REGISTRY["brands"].items():
        loaded_brand = loaded_brands.get(brand_id) or {}
        merged = {**default_brand, **loaded_brand}
        for key in ["approval_rules", "integrations", "provider_rules", "pricing_rules", "mockup_preferences"]:
            if isinstance(default_brand.get(key), dict) and isinstance(loaded_brand.get(key), dict):
                if key == "integrations":
                    merged[key] = {
                        provider: {**(default_brand.get(key, {}).get(provider) or {}), **(loaded_brand.get(key, {}).get(provider) or {})}
                        for provider in set(default_brand.get(key, {})) | set(loaded_brand.get(key, {}))
                    }
                else:
                    merged[key] = {**default_brand.get(key, {}), **loaded_brand.get(key, {})}
        brands[brand_id] = _apply_current_provider_defaults(brand_id, merged)
    for brand_id, loaded_brand in loaded_brands.items():
        if brand_id not in brands:
            brands[brand_id] = loaded_brand
    return {"brands": brands}


def list_brands(path: Path | None = None) -> dict[str, Any]:
    registry = load_brand_registry(path)
    brands = list(registry["brands"].values())
    return {
        "status": "ok",
        "brands": brands,
        "brand_count": len(brands),
        "enabled_brand_count": len([brand for brand in brands if brand.get("enabled")]),
        "execution_enabled": False,
        "writes_enabled": False,
    }


def get_brand(brand_id: str, path: Path | None = None) -> dict[str, Any]:
    registry = load_brand_registry(path)
    key = brand_id.strip().lower()
    brand = registry["brands"].get(key)
    if brand is None:
        for item in registry["brands"].values():
            if str(item.get("display_name", "")).strip().lower() == key:
                brand = item
                break
    if brand is None:
        raise KeyError(f"Unknown brand: {brand_id}")
    return brand


def get_default_brand(path: Path | None = None) -> dict[str, Any]:
    registry = load_brand_registry(path)
    for brand in registry["brands"].values():
        if brand.get("default"):
            return brand
    return next(iter(registry["brands"].values()))


def validate_brand_product_niche(brand_id: str, product_type: str, niche: str, path: Path | None = None) -> dict[str, Any]:
    brand = get_brand(brand_id, path)
    product_matches = _contains_any(product_type, list(brand.get("blocked_product_types") or []))
    niche_matches = _contains_any(niche, list(brand.get("blocked_niches") or []))
    blocked_terms = sorted(set(product_matches + niche_matches))
    if product_matches:
        return _validation_result(False, brand, "Product type is blocked for this brand.", blocked_terms)
    if niche_matches:
        return _validation_result(False, brand, "Niche is blocked for this brand.", blocked_terms)

    for rule in brand.get("blocked_product_niche_pairs") or []:
        product_terms = [str(item) for item in rule.get("product_terms") or []]
        niche_terms = [str(item) for item in rule.get("niche_terms") or []]
        matched_products = _contains_any(product_type, product_terms)
        matched_niches = _contains_any(niche, niche_terms)
        if matched_products and matched_niches:
            return _validation_result(
                False,
                brand,
                str(rule.get("reason") or "Product/niche pair is blocked for this brand."),
                sorted(set(matched_products + matched_niches)),
            )

    return _validation_result(True, brand, "Product/niche pair is allowed for this brand.", [])


def _validation_result(allowed: bool, brand: dict[str, Any], reason: str, blocked_terms: list[str]) -> dict[str, Any]:
    return {
        "status": "allowed" if allowed else "blocked",
        "compatible": allowed,
        "brand_id": brand["brand_id"],
        "brand_name": brand["display_name"],
        "brand_voice": brand.get("brand_voice", ""),
        "brand_compatibility_status": "allowed" if allowed else "blocked",
        "brand_compatibility_reason": reason,
        "compatibility_status": "allowed" if allowed else "blocked",
        "compatibility_reason": reason,
        "blocked_terms": blocked_terms,
        "execution_enabled": False,
        "writes_enabled": False,
        "publishing_enabled": False,
        "upload_enabled": False,
        "order_enabled": False,
        "send_enabled": False,
    }


def brand_health(path: Path | None = None) -> dict[str, Any]:
    initialize_brand_registry(path)
    brands = list_brands(path)
    default_brand = get_default_brand(path)
    return {
        "status": "ok",
        "registry_path": str(path or REGISTRY_PATH),
        "brand_count": brands["brand_count"],
        "enabled_brand_count": brands["enabled_brand_count"],
        "default_brand": default_brand["brand_id"],
        "execution_enabled": False,
        "writes_enabled": False,
        "publishing_enabled": False,
    }


def write_brand_report(path: Path | None = None, report_path: Path | None = None) -> dict[str, Any]:
    report = report_path or REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    brands = list_brands(path)["brands"]
    default_brand = get_default_brand(path)
    lines = [
        "# Brand Registry",
        "",
        f"Updated: {_now()}",
        "",
        "## Safety",
        "",
        "- External writes are disabled.",
        "- Etsy writes are disabled.",
        "- Printify writes are disabled.",
        "- ComfyUI execution is disabled.",
        "- Publishing, uploads, orders, and sending are disabled.",
        "",
        "## Summary",
        "",
        f"- Brands: {len(brands)}",
        f"- Enabled brands: {len([brand for brand in brands if brand.get('enabled')])}",
        f"- Default brand: {default_brand.get('display_name')}",
        "",
        "## Brands",
        "",
    ]
    for brand in brands:
        lines.extend([
            f"### {brand.get('display_name')}",
            "",
            f"- Brand ID: {brand.get('brand_id')}",
            f"- Enabled: {brand.get('enabled')}",
            f"- Default: {brand.get('default')}",
            f"- Shop type: {brand.get('shop_type')}",
            f"- Etsy writes enabled: {brand.get('integrations', {}).get('etsy', {}).get('writes_enabled', False)}",
            f"- Printify writes enabled: {brand.get('integrations', {}).get('printify', {}).get('writes_enabled', False)}",
            f"- ComfyUI execution enabled: {brand.get('integrations', {}).get('comfyui', {}).get('execution_enabled', False)}",
            "",
        ])
    report.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report_path": str(report), "brand_count": len(brands)}
