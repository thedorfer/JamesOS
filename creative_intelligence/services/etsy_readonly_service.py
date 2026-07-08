from __future__ import annotations

from typing import Any

from creative_intelligence.config import READONLY_SAFETY, etsy_public_config
from creative_intelligence.storage.sqlite import (
    list_performance_history,
    performance_history_exists,
    performance_summary,
    rebuild_performance_history_from_local_tables,
    record_etsy_sync_run,
)


SAFE_MESSAGE = "Etsy connector is read-only. Sales intelligence may learn from imported orders across POD providers, but no listing, message, fulfillment, Printify, InkedJoy, ComfyUI, or image-upload writes are implemented."


def _safe_response(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {**READONLY_SAFETY, **(payload or {})}


def _configured() -> bool:
    config = etsy_public_config()
    return bool(
        config["enabled"]
        and config["readonly"]
        and config["shop_id_configured"]
        and config["access_token_configured"]
    )


def health() -> dict[str, Any]:
    config = etsy_public_config()
    status = "ok" if _configured() else "not_configured"
    return _safe_response(
        {
            "status": status,
            "service": "etsy_readonly",
            "shop_name": config["shop_name"],
            "configured": _configured(),
            "config": config,
            "message": SAFE_MESSAGE,
        }
    )


def auth_status() -> dict[str, Any]:
    config = etsy_public_config()
    missing = [
        key
        for key, configured in {
            "ETSY_ENABLED": config["enabled"],
            "ETSY_READONLY": config["readonly"],
            "ETSY_SHOP_ID": config["shop_id_configured"],
            "ETSY_ACCESS_TOKEN": config["access_token_configured"],
        }.items()
        if not configured
    ]
    return _safe_response(
        {
            "status": "configured" if not missing else "not_configured",
            "configured": not missing,
            "missing": missing,
            "shop_name": config["shop_name"],
        }
    )


def sync_shop_readonly() -> dict[str, Any]:
    if not _configured():
        run = record_etsy_sync_run("shop", "not_configured", "Missing Etsy read-only configuration.")
        return _safe_response({"status": "not_configured", "run": run})
    run = record_etsy_sync_run("shop", "placeholder", "Read-only shop sync placeholder; no Etsy API call made.")
    return _safe_response({"status": "placeholder", "run": run})


def sync_listings_readonly() -> dict[str, Any]:
    if not _configured():
        run = record_etsy_sync_run("listings", "not_configured", "Missing Etsy read-only configuration.")
        return _safe_response({"status": "not_configured", "run": run, "listings_synced": 0})
    run = record_etsy_sync_run("listings", "placeholder", "Read-only listings sync placeholder; no Etsy API call made.")
    return _safe_response({"status": "placeholder", "run": run, "listings_synced": 0})


def sync_receipts_readonly() -> dict[str, Any]:
    if not _configured():
        run = record_etsy_sync_run("receipts", "not_configured", "Missing Etsy read-only configuration.")
        return _safe_response({"status": "not_configured", "run": run, "receipts_synced": 0})
    run = record_etsy_sync_run("receipts", "placeholder", "Read-only receipts sync placeholder; no Etsy API call made.")
    return _safe_response({"status": "placeholder", "run": run, "receipts_synced": 0})


def sync_shop_readonly_all() -> dict[str, Any]:
    shop = sync_shop_readonly()
    listings = sync_listings_readonly()
    receipts = sync_receipts_readonly()
    history = rebuild_performance_history()
    statuses = {shop["status"], listings["status"], receipts["status"], history["status"]}
    status = "not_configured" if statuses == {"not_configured"} else "ok"
    return _safe_response(
        {
            "status": status,
            "shop": shop,
            "listings": listings,
            "receipts": receipts,
            "performance_history": history,
        }
    )


def sync_shop_readonly_bundle() -> dict[str, Any]:
    return sync_shop_readonly_all()


def sync_readonly() -> dict[str, Any]:
    return sync_shop_readonly_all()


def rebuild_performance_history() -> dict[str, Any]:
    result = rebuild_performance_history_from_local_tables()
    status = "ok" if result.get("rebuilt", 0) else "not_configured"
    if status == "not_configured" and _configured():
        status = "empty"
    return _safe_response({**result, "status": status})


def get_performance_summary() -> dict[str, Any]:
    summary = performance_summary()
    status = "ok" if performance_history_exists() else "not_configured"
    return _safe_response({"status": status, "summary": summary})


def get_top_products(limit: int = 10) -> dict[str, Any]:
    products = list_performance_history(limit=limit, order_by="revenue", ascending=False)
    status = "ok" if products else "not_configured"
    return _safe_response({"status": status, "products": products})


def get_underperforming_products(limit: int = 10) -> dict[str, Any]:
    products = list_performance_history(limit=limit, order_by="conversion_rate", ascending=True)
    products = [product for product in products if int(product.get("views") or 0) >= 25]
    status = "ok" if products else "not_configured"
    return _safe_response({"status": status, "products": products[:limit]})
