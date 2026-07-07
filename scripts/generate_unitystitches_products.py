#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from jamesos.services.unitystitches_product_pipeline import (
    drafts_for_date,
    generate_daily_product_drafts,
    health,
    list_drafts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate UnityStitches draft-only product packages.")
    sub = parser.add_subparsers(dest="command")

    generate = sub.add_parser("generate", help="Generate daily draft packages")
    generate.add_argument("--date", default="", help="YYYY-MM-DD date override")

    sub.add_parser("health", help="Show pipeline health")
    sub.add_parser("list", help="Show all draft packages")

    show = sub.add_parser("show-date", help="Show drafts for a date")
    show.add_argument("date")

    args = parser.parse_args()
    command = args.command or "generate"

    if command == "health":
        result = health()
    elif command == "list":
        result = list_drafts()
    elif command == "show-date":
        result = drafts_for_date(args.date)
    else:
        result = generate_daily_product_drafts(run_date=args.date or None)

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
