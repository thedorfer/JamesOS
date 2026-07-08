#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jamesos.services.design_variation_service import create_design_run, promote_best, score_design_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local recipe-driven design run. Does not execute image jobs.")
    parser.add_argument("--brand", "--brand-id", dest="brand_id", default="unitystitches")
    parser.add_argument("--product", "--product-type", dest="product_type", default="womens_underwear")
    parser.add_argument("--niche", default="trans pride")
    parser.add_argument("--recipe", "--recipe-id", dest="recipe_id", default="underwear/pride_pattern")
    parser.add_argument("--variations", type=int, default=4)
    parser.add_argument("--quality", default="premium")
    parser.add_argument("--provider", default="printify")
    parser.add_argument("--promote", action="store_true", help="Also promote the best pre-generation candidate.")
    args = parser.parse_args()

    run = create_design_run(
        brand_id=args.brand_id,
        product_type=args.product_type,
        niche=args.niche,
        recipe_id=args.recipe_id,
        variations=args.variations,
        quality=args.quality,
        provider=args.provider,
        create_image_jobs=True,
    )
    scored = score_design_run(run["run_id"])["run"]
    best = max(scored["variations"], key=lambda item: int(item["score"]["print_readiness_score"]))
    result = {
        "status": "ok",
        "run_id": run["run_id"],
        "run_folder": run["run_folder"],
        "variation_count": run["variation_count"],
        "best_pre_generation_candidate": {
            "variation_id": best["variation_id"],
            "score": best["score"]["print_readiness_score"],
            "status": "ready_for_printify_review" if best["score"]["print_readiness_score"] >= 90 and args.provider == "printify" else "best_candidate_needs_review",
            "image_job_id": best.get("image_job_id", ""),
        },
        "image_job_commands": [
            {
                "variation_id": variation["variation_id"],
                "approve": f"python3 scripts/job_queue.py approve {variation.get('image_job_id', 'JOB_ID')}",
                "execute": f"curl -X POST -H \"X-JamesOS-Key: $JAMESOS_API_KEY\" http://localhost:8787/image-worker/jobs/{variation.get('image_job_id', 'JOB_ID')}/execute-approved",
            }
            for variation in scored["variations"]
            if variation.get("image_job_id")
        ],
        "safety": scored["safety"],
        "note": "No image jobs were auto-executed. No provider APIs were called.",
    }
    if args.promote:
        result["promotion"] = promote_best(run["run_id"])["winner"]
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
