#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from jamesos.integrations.printify_client import PrintifyClient
from jamesos.services import printify_product


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Printify and create approval-bound unpublished product drafts.",
        epilog="Writes are separate: upload requires --confirm-upload; create-draft requires --confirm-create-draft. No publish or order operations exist.")
    parser.add_argument("mode", choices=("status", "shops", "search-shirts", "providers", "variants", "shipping", "plan", "upload", "create-draft", "fetch-product", "download-mockups"))
    parser.add_argument("--job-id"); parser.add_argument("--shop-id", type=int); parser.add_argument("--blueprint-id", type=int)
    parser.add_argument("--print-provider-id", type=int); parser.add_argument("--variant-id", type=int, action="append", default=[])
    parser.add_argument("--price", type=int, default=2499); parser.add_argument("--placeholder-width", type=int)
    parser.add_argument("--placeholder-height", type=int); parser.add_argument("--scale", type=float)
    parser.add_argument("--confirm-upload", action="store_true"); parser.add_argument("--confirm-create-draft", action="store_true")
    args = parser.parse_args(); client = PrintifyClient()
    if args.mode == "status": result = printify_product.status()
    elif args.mode == "shops": result = {"shops": printify_product.normalize_shops(client.list_shops())}
    elif args.mode == "search-shirts": result = {"blueprints": printify_product.search_shirt_blueprints(client)}
    elif args.mode == "providers": result = client.list_print_providers_for_blueprint(args.blueprint_id)
    elif args.mode == "variants": result = client.get_variants(args.blueprint_id, args.print_provider_id)
    elif args.mode == "shipping": result = client.get_shipping(args.blueprint_id, args.print_provider_id)
    elif args.mode == "upload": result = printify_product.upload_approved_artwork(args.job_id or "", confirmed=args.confirm_upload, client=client)
    elif args.mode == "plan":
        evidence = printify_product._approved_evidence(args.job_id or "")
        upload_path = evidence["job_root"] / "commerce" / "printify" / "upload.json"
        upload = json.loads(upload_path.read_text(encoding="utf-8"))
        required = (args.shop_id, args.blueprint_id, args.print_provider_id, args.placeholder_width, args.placeholder_height)
        if any(value is None for value in required) or not args.variant_id: parser.error("plan requires shop, blueprint, provider, placeholder dimensions, and variant IDs")
        result = printify_product.create_draft_plan(args.job_id, upload=upload, shop_id=args.shop_id,
            blueprint_id=args.blueprint_id, provider_id=args.print_provider_id, enabled_variant_ids=args.variant_id,
            prices={item: args.price for item in args.variant_id}, placeholder=(args.placeholder_width, args.placeholder_height), requested_scale=args.scale)
    elif args.mode == "create-draft":
        required = (args.shop_id, args.blueprint_id, args.print_provider_id)
        if any(value is None for value in required) or not args.variant_id:
            parser.error("create-draft requires shop, blueprint, provider, and repeated variant IDs")
        evidence = printify_product._approved_evidence(args.job_id or "")
        plan = json.loads((evidence["job_root"] / "commerce" / "printify" / "product-draft-plan.json").read_text(encoding="utf-8"))
        supplied = (args.shop_id, args.blueprint_id, args.print_provider_id, sorted(set(args.variant_id)))
        planned = (plan["shop_id"], plan["blueprint_id"], plan["print_provider_id"], plan["enabled_variant_ids"])
        if supplied != planned: parser.error("create-draft selections must exactly match the immutable draft plan")
        result = printify_product.create_product_draft(args.job_id or "", confirmed=args.confirm_create_draft, client=client)
    elif args.mode == "fetch-product":
        evidence = printify_product._approved_evidence(args.job_id or ""); path = evidence["job_root"] / "commerce" / "printify" / "product-draft.json"
        record = json.loads(path.read_text(encoding="utf-8")); result = client.get_product(record["shop_id"], record["printify_product_id"])
    else: result = {"mockups": printify_product.download_mockups(args.job_id or "", client=client)}
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
