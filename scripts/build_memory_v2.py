#!/usr/bin/env python3
from __future__ import annotations

import argparse

from jamesos.services.memory_v2 import build_memory_v2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Memory V2 entity and timeline pages.")
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        default=6,
        help="Maximum source mentions per entity (default: 6)",
    )
    parser.add_argument(
        "--people-threshold",
        type=int,
        default=None,
        help="Promote email contacts with at least this many messages (default: 5)",
    )
    parser.add_argument(
        "--include-all-contacts",
        action="store_true",
        help="Generate People pages for all raw email contacts",
    )
    args = parser.parse_args(argv)
    print("Building Memory V2...")
    res = build_memory_v2(
        limit_per_entity=args.limit,
        people_threshold=args.people_threshold,
        include_all_contacts=args.include_all_contacts,
    )
    built_counts = {name: len(paths) for name, paths in res["built"].items()}
    print("Done.")
    print("Built:", built_counts)
    print("People:", res["people"])
    print("Report:", res["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
