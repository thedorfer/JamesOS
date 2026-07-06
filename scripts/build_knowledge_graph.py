#!/usr/bin/env python3
from __future__ import annotations

import argparse

from jamesos.services.knowledge_graph_service import build_knowledge_graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build synthesized JamesOS Knowledge Graph wiki pages."
    )
    parser.add_argument(
        "limit",
        nargs="?",
        type=int,
        default=6,
        help="Maximum evidence links per entity (default: 6)",
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

    print("Building Knowledge Graph...")
    result = build_knowledge_graph(
        limit_per_entity=args.limit,
        people_threshold=args.people_threshold,
        include_all_contacts=args.include_all_contacts,
    )
    counts = {name: len(paths) for name, paths in result["built"].items()}
    print("Done.")
    print("Built:", counts)
    print("People:", result["people"])
    print("Report:", result["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
