from __future__ import annotations

from pathlib import Path
import os

from jamesos.config import VAULT


DATA_ROOT = VAULT / "JamesOS" / "CreativeIntelligence"
DB_PATH = DATA_ROOT / "creative_intelligence.db"

ETSY_ENABLED = os.getenv("ETSY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
ETSY_READONLY = os.getenv("ETSY_READONLY", "true").strip().lower() not in {"0", "false", "no", "off"}
ETSY_API_KEY = os.getenv("ETSY_API_KEY", "")
ETSY_CLIENT_ID = os.getenv("ETSY_CLIENT_ID", "")
ETSY_CLIENT_SECRET = os.getenv("ETSY_CLIENT_SECRET", "")
ETSY_REDIRECT_URI = os.getenv("ETSY_REDIRECT_URI", "")
ETSY_ACCESS_TOKEN = os.getenv("ETSY_ACCESS_TOKEN", "")
ETSY_REFRESH_TOKEN = os.getenv("ETSY_REFRESH_TOKEN", "")
ETSY_SHOP_ID = os.getenv("ETSY_SHOP_ID", "")
ETSY_SHOP_NAME = os.getenv("ETSY_SHOP_NAME", "Commerce Shop")

ETSY_CONFIG_FIELDS = {
    "ETSY_ENABLED": ETSY_ENABLED,
    "ETSY_READONLY": ETSY_READONLY,
    "ETSY_API_KEY": ETSY_API_KEY,
    "ETSY_CLIENT_ID": ETSY_CLIENT_ID,
    "ETSY_CLIENT_SECRET": ETSY_CLIENT_SECRET,
    "ETSY_REDIRECT_URI": ETSY_REDIRECT_URI,
    "ETSY_ACCESS_TOKEN": ETSY_ACCESS_TOKEN,
    "ETSY_REFRESH_TOKEN": ETSY_REFRESH_TOKEN,
    "ETSY_SHOP_ID": ETSY_SHOP_ID,
    "ETSY_SHOP_NAME": ETSY_SHOP_NAME,
}

READONLY_SAFETY = {
    "readonly": True,
    "writes_enabled": False,
    "publishing_enabled": False,
    "order_fulfillment_enabled": False,
}

DEFAULT_TREND_SEEDS = [
    "personalized gifts",
    "minimalist wall art",
    "teacher appreciation",
    "pet memorial keepsakes",
    "cozy office decor",
    "family reunion shirts",
    "local business branding",
]

DEFAULT_AUDIENCES = [
    "busy parents",
    "small business owners",
    "teachers",
    "pet owners",
    "remote workers",
    "gift shoppers",
]

DEFAULT_PRODUCT_TYPES = [
    "t-shirt",
    "hoodie",
    "mug",
    "poster",
    "sticker",
    "tote bag",
]


def ensure_data_root() -> Path:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    return DATA_ROOT


def etsy_public_config() -> dict[str, object]:
    """Return Etsy config status without exposing tokens or client secrets."""
    return {
        "enabled": ETSY_ENABLED,
        "readonly": ETSY_READONLY,
        "shop_id_configured": bool(ETSY_SHOP_ID),
        "shop_name": ETSY_SHOP_NAME,
        "api_key_configured": bool(ETSY_API_KEY),
        "client_id_configured": bool(ETSY_CLIENT_ID),
        "client_secret_configured": bool(ETSY_CLIENT_SECRET),
        "redirect_uri_configured": bool(ETSY_REDIRECT_URI),
        "access_token_configured": bool(ETSY_ACCESS_TOKEN),
        "refresh_token_configured": bool(ETSY_REFRESH_TOKEN),
    }
