#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from jamesos.services.design_planner import create_design_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local Design Planner artifact.")
    parser.add_argument("--brand", "--brand-id", dest="brand_id", default="commerce_shop")
    parser.add_argument("--product", "--product-type", dest="product_type", default="womens_underwear")
    parser.add_argument("--niche", default="trans pride")
    parser.add_argument("--recipe", "--recipe-id", dest="recipe_id", default="underwear/pride_pattern")
    parser.add_argument("--quality-target", type=int, default=90)
    args = parser.parse_args()

    plan = create_design_plan(
        brand_id=args.brand_id,
        product_type=args.product_type,
        niche=args.niche,
        recipe_id=args.recipe_id,
        quality_target=args.quality_target,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
