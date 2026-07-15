#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from jamesos.integrations.printify_client import PrintifyClient
from jamesos.services import printify_product, sale_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Guided, separately confirmed JamesOS sale-candidate workflow.")
    parser.add_argument("mode", choices=("replay", "profile-store", "compose", "approve-composition", "generate-listing",
        "approve-listing", "upload", "create-draft", "download-mockups", "build-report"))
    parser.add_argument("--job-id", required=True); parser.add_argument("--composition-id"); parser.add_argument("--font-path", type=Path)
    parser.add_argument("--run-path", type=Path); parser.add_argument("--report-path", type=Path)
    parser.add_argument("--shop-id", type=int, default=9437076); parser.add_argument("--product-id")
    parser.add_argument("--blueprint-id", type=int); parser.add_argument("--print-provider-id", type=int)
    parser.add_argument("--variant-id", type=int, action="append", default=[]); parser.add_argument("--price", type=int, default=2499)
    parser.add_argument("--scale", type=float, default=.85); parser.add_argument("--approved-by", default="James")
    for flag in ("confirm-compose", "confirm-composition-approval", "confirm-listing-generation", "confirm-listing-approval", "confirm-upload", "confirm-create-draft"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args(); client = PrintifyClient(); evidence = printify_product._approved_evidence(args.job_id)
    run_path = args.run_path or evidence["job_root"] / "commerce" / "sale-candidates" / (args.composition_id or "baseline") / "sale-candidate-run.json"
    report_path = args.report_path or run_path.with_name("sale-candidate-report.html")
    if args.mode == "replay":
        run = sale_candidate.replay_baseline(args.job_id, args.product_id or "6a57eaa752f2c3e4700dbf23", args.shop_id, client=client, report_path=report_path)
        print(json.dumps({"result": "replayed", "report_path": str(report_path), "run": run}, indent=2)); return 0
    composition_root = evidence["job_root"] / "commerce" / "product-compositions" / (args.composition_id or "")
    profile_path = evidence["job_root"] / "commerce" / "printify" / "unitystitches-style-profile.json"
    if args.mode == "profile-store": result = sale_candidate.profile_store(client, args.shop_id, profile_path)
    elif args.mode == "compose": result = sale_candidate.create_composition(args.job_id, args.composition_id or "", font_path=args.font_path or Path(""), confirmed=args.confirm_compose)
    elif args.mode == "approve-composition": result = sale_candidate.approve_composition(args.job_id, args.composition_id or "", approved_by=args.approved_by, confirmed=args.confirm_composition_approval)
    elif args.mode == "generate-listing": result = sale_candidate.generate_listing(composition_root, profile_path, confirmed=args.confirm_listing_generation)
    elif args.mode == "approve-listing": result = sale_candidate.approve_listing(composition_root / "listing", approved_by=args.approved_by, confirmed=args.confirm_listing_approval)
    elif args.mode == "upload": result = sale_candidate.upload_composition(args.job_id, args.composition_id or "", client=client, confirmed=args.confirm_upload)
    elif args.mode == "create-draft": result = sale_candidate.create_composition_product_draft(args.job_id, args.composition_id or "", client=client,
        confirmed=args.confirm_create_draft, shop_id=args.shop_id, blueprint_id=args.blueprint_id, provider_id=args.print_provider_id,
        variant_ids=args.variant_id, price=args.price, scale=args.scale)
    elif args.mode == "download-mockups": result = {"mockups": sale_candidate.download_composition_mockups(args.job_id, args.composition_id or "", client=client)}
    else:
        run = json.loads(run_path.read_text(encoding="utf-8")); sale_candidate.build_html_report(run, report_path); result = {"report_path": str(report_path)}
    transition = {"stage": args.mode, "timestamp": datetime.now().astimezone().isoformat(), "result_sha256": sale_candidate.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()}
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {"run_id": args.composition_id, "artwork_job_id": args.job_id,
        "composition_id": args.composition_id, "listing_package_id": None, "printify_upload_id": None, "printify_product_id": None,
        "transitions": [], "hashes": {}, "approvals": {}, "publish_status": "not_published", "order_status": "not_created"}
    run["transitions"].append(transition); run["current_next_action"] = {"compose":"approve-composition", "approve-composition":"generate-listing",
        "generate-listing":"approve-listing", "approve-listing":"upload", "upload":"create-draft", "create-draft":"download-mockups"}.get(args.mode, "human_review")
    run.setdefault("hashes", {})[args.mode] = transition["result_sha256"]
    if args.mode == "profile-store": run["style_profile"] = result
    elif args.mode == "compose":
        run["composition"] = result; run["approved_artwork_path"] = result["approved_source_candidate_path"]
        run["product_brief"] = {"product_type": "unisex_t_shirt", "exact_text": "LOVE IS LOVE",
            "layout": "arched_headline_above_artwork", "preferred_mockup_color": "Black"}
    elif args.mode == "approve-composition": run.setdefault("approvals", {})["composition"] = result
    elif args.mode == "generate-listing": run["listing"] = result; run["listing_package_id"] = result["listing_package_id"]
    elif args.mode == "approve-listing": run.setdefault("approvals", {})["listing"] = result
    elif args.mode == "upload": run["printify_upload"] = result; run["printify_upload_id"] = result["printify_image_id"]
    elif args.mode == "create-draft": run["printify_product"] = result; run["printify_product_id"] = result["product_id"]
    elif args.mode == "download-mockups": run["mockups"] = result["mockups"]
    run_path.parent.mkdir(parents=True, exist_ok=True); run_path.write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"result": result, "run_path": str(run_path), "next_action": run["current_next_action"]}, indent=2, default=str)); return 0


if __name__ == "__main__": raise SystemExit(main())
