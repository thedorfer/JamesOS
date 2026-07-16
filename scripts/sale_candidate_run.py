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
from jamesos.services.error_handler import cli_error, handle_error
from jamesos.services import printify_product, sale_candidate, sale_candidate_vector
from jamesos.core.profiles.selection import commerce_configuration


def _main() -> int:
    parser = argparse.ArgumentParser(description="Guided, separately confirmed JamesOS sale-candidate workflow.")
    parser.add_argument("mode", choices=("font-acquisition-plan", "acquire-fonts", "list-design-concepts", "preview-design-concepts",
        "approve-design-concept", "show-design-selection", "replay", "profile-store", "compose", "approve-composition", "list-fonts", "preview-fonts",
        "approve-font", "show-font-selection", "generate-listing", "approve-listing", "upload", "create-draft", "download-mockups", "build-report"))
    parser.add_argument("--job-id"); parser.add_argument("--composition-id"); parser.add_argument("--font-path", type=Path)
    parser.add_argument("--phrase", default="SAMPLE"); parser.add_argument("--font-option-id"); parser.add_argument("--preview-run-id")
    parser.add_argument("--concept-id"); parser.add_argument("--design-run-id")
    parser.add_argument("--run-path", type=Path); parser.add_argument("--report-path", type=Path)
    parser.add_argument("--shop-id", type=int); parser.add_argument("--product-id")
    parser.add_argument("--blueprint-id", type=int); parser.add_argument("--print-provider-id", type=int)
    parser.add_argument("--variant-id", type=int, action="append", default=[]); parser.add_argument("--price", type=int, default=2499)
    parser.add_argument("--scale", type=float, default=.85); parser.add_argument("--approved-by", default="James")
    for flag in ("confirm-font-download", "confirm-design-approval", "confirm-compose", "confirm-composition-approval", "confirm-preview-generation", "confirm-font-approval", "confirm-listing-generation", "confirm-listing-approval", "confirm-upload", "confirm-create-draft"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args()
    if args.mode == "list-fonts":
        print(json.dumps({"fonts": sale_candidate.list_curated_fonts()}, indent=2)); return 0
    if args.mode == "font-acquisition-plan":
        print(json.dumps(sale_candidate_vector.font_acquisition_plan(), indent=2)); return 0
    if args.mode == "acquire-fonts":
        result = sale_candidate_vector.acquire_fonts(confirmed=args.confirm_font_download)
        print(json.dumps(result, indent=2)); return 0
    if not args.job_id: parser.error("--job-id is required for this mode")
    client = PrintifyClient(); evidence = printify_product._approved_evidence(args.job_id)
    run_path = args.run_path or evidence["job_root"] / "commerce" / "sale-candidates" / (args.composition_id or "baseline") / "sale-candidate-run.json"
    report_path = args.report_path or run_path.with_name("sale-candidate-report.html")
    if args.mode == "replay":
        config=commerce_configuration();product_id=args.product_id or config.get("baseline_product_id");shop_id=args.shop_id or config.get("printify_shop_id")
        if not product_id or not shop_id:parser.error("replay requires profile IDs or explicit --product-id and --shop-id")
        run = sale_candidate.replay_baseline(args.job_id, str(product_id), int(shop_id), client=client, report_path=report_path)
        print(json.dumps({"result": "replayed", "report_path": str(report_path), "run": run}, indent=2)); return 0
    composition_root = evidence["job_root"] / "commerce" / "product-compositions" / (args.composition_id or "")
    profile_path = evidence["job_root"] / "commerce" / "printify" / "commerce_shop-style-profile.json"
    if args.mode == "profile-store": result = sale_candidate.profile_store(client, args.shop_id, profile_path)
    elif args.mode == "preview-design-concepts": result = sale_candidate_vector.generate_design_concepts(args.job_id, args.composition_id or "",
        phrase=args.phrase, confirmed=args.confirm_preview_generation, run_id=args.design_run_id)
    elif args.mode == "approve-design-concept":
        runs = sorted((composition_root / "design-runs").glob("*/design-concept-manifest.json")); design_run_id = args.design_run_id or (runs[-1].parent.name if runs else "")
        result = sale_candidate_vector.approve_design_concept(args.job_id, args.composition_id or "", design_run_id=design_run_id,
            concept_id=args.concept_id or "", approved_by=args.approved_by, confirmed=args.confirm_design_approval)
    elif args.mode == "show-design-selection": result = sale_candidate_vector.show_design_selection(args.job_id, args.composition_id or "")
    elif args.mode == "list-design-concepts":
        runs = sorted((composition_root / "design-runs").glob("*/design-concept-manifest.json"))
        if not runs: raise SystemExit("No v3 design concept manifest exists.")
        manifest = json.loads(runs[-1].read_text(encoding="utf-8")); result = {"design_run_id": manifest["design_run_id"],
            "concepts": [{"concept_id": item["concept_id"], "layout_structure": item["layout_structure"], "treatment_id": item["treatment_id"], "status": item["status"]} for item in manifest["concepts"]]}
    elif args.mode == "preview-fonts": result = sale_candidate.generate_font_previews(args.job_id, args.composition_id or "", phrase=args.phrase,
        confirmed=args.confirm_preview_generation, preview_run_id=args.preview_run_id)
    elif args.mode == "approve-font":
        runs = sorted((composition_root / "font-preview-runs").glob("*/font-preview-manifest.json"))
        preview_run_id = args.preview_run_id or (runs[-1].parent.name if runs else "")
        result = sale_candidate.approve_font_selection(args.job_id, args.composition_id or "", preview_run_id=preview_run_id,
            font_option_id=args.font_option_id or "", approved_by=args.approved_by, confirmed=args.confirm_font_approval)
    elif args.mode == "show-font-selection": result = sale_candidate.get_font_selection(args.job_id, args.composition_id or "")
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
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if run.get("font_manifest"):
            sale_candidate.build_font_preview_report(run["font_manifest"], report_path, run.get("font_selection"))
        else: sale_candidate.build_html_report(run, report_path)
        result = {"report_path": str(report_path)}
    transition = {"stage": args.mode, "timestamp": datetime.now().astimezone().isoformat(), "result_sha256": sale_candidate.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()}
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {"run_id": args.composition_id, "artwork_job_id": args.job_id,
        "composition_id": args.composition_id, "listing_package_id": None, "printify_upload_id": None, "printify_product_id": None,
        "transitions": [], "hashes": {}, "approvals": {}, "publish_status": "not_published", "order_status": "not_created"}
    run["transitions"].append(transition); run["current_next_action"] = {"preview-design-concepts":"approve-design-concept", "approve-design-concept":"generate-listing", "preview-fonts":"approve-font", "approve-font":"generate-listing", "compose":"approve-composition", "approve-composition":"generate-listing",
        "generate-listing":"approve-listing", "approve-listing":"upload", "upload":"create-draft", "create-draft":"download-mockups"}.get(args.mode, "human_review")
    run.setdefault("hashes", {})[args.mode] = transition["result_sha256"]
    if args.mode == "profile-store": run["style_profile"] = result
    elif args.mode == "preview-design-concepts": run["design_manifest"] = result; run["approved_artwork_path"] = result["approved_source_path"]
    elif args.mode == "approve-design-concept": run["design_selection"] = result; run.setdefault("approvals", {})["design_selection"] = result
    elif args.mode == "preview-fonts":
        run["font_manifest"] = {key: value for key, value in result.items() if key not in ("manifest_path", "manifest_sha256", "report_path")}
        run["approved_artwork_path"] = result["approved_base_artwork_path"]
        run["product_brief"] = {"product_type": "unisex_t_shirt", "exact_text": args.phrase, "preferred_mockup_color": "Black"}
    elif args.mode == "approve-font": run["font_selection"] = result; run.setdefault("approvals", {})["font_selection"] = result
    elif args.mode == "compose":
        run["composition"] = result; run["approved_artwork_path"] = result["approved_source_candidate_path"]
        run["product_brief"] = {"product_type": "unisex_t_shirt", "exact_text": "SAMPLE",
            "layout": "arched_headline_above_artwork", "preferred_mockup_color": "Black"}
    elif args.mode == "approve-composition": run.setdefault("approvals", {})["composition"] = result
    elif args.mode == "generate-listing": run["listing"] = result; run["listing_package_id"] = result["listing_package_id"]
    elif args.mode == "approve-listing": run.setdefault("approvals", {})["listing"] = result
    elif args.mode == "upload": run["printify_upload"] = result; run["printify_upload_id"] = result["printify_image_id"]
    elif args.mode == "create-draft": run["printify_product"] = result; run["printify_product_id"] = result["product_id"]
    elif args.mode == "download-mockups": run["mockups"] = result["mockups"]
    run_path.parent.mkdir(parents=True, exist_ok=True); run_path.write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"result": result, "run_path": str(run_path), "next_action": run["current_next_action"]}, indent=2, default=str)); return 0


def main() -> int:
    try:
        return _main()
    except Exception as exc:
        envelope = handle_error(exc, operation="sale_candidate_cli")
        print(json.dumps(cli_error(envelope), indent=2)); return 1


if __name__ == "__main__": raise SystemExit(main())
