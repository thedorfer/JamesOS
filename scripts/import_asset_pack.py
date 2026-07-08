#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from jamesos.services.asset_pack_importer import import_asset_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a reusable Creative Studio asset pack.")
    parser.add_argument("source", help="Folder, zip, or single asset file to import.")
    parser.add_argument("--name", "--pack-name", dest="pack_name", default="")
    parser.add_argument("--category", default="")
    parser.add_argument("--source", dest="license_source", default="")
    parser.add_argument("--license", dest="license_name", default="")
    parser.add_argument("--commercial-allowed", action="store_true")
    parser.add_argument("--attribution-required", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    result = import_asset_pack(
        args.source,
        pack_name=args.pack_name or None,
        category=args.category or None,
        license_metadata={
            "source": args.license_source,
            "license": args.license_name,
            "commercial_allowed": bool(args.commercial_allowed),
            "attribution_required": bool(args.attribution_required),
            "notes": args.notes,
        },
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
