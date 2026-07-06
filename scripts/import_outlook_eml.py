#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from jamesos.services.email_importer import import_eml_directory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import recursively exported Outlook .eml files into JamesOS.",
        epilog=(
            "Example: PYTHONPATH=. python3 scripts/import_outlook_eml.py "
            "~/JamesOSData/Imports/OutlookPST/backup_eml"
        ),
    )
    parser.add_argument("source", type=Path, help="Directory containing exported .eml files")
    args = parser.parse_args()

    result = import_eml_directory(args.source)
    print(
        f"Outlook email import {result['status']}: "
        f"{result['imported']}/{result['found']} imported, {result['failed']} failed."
    )
    for failure in result["failures"][:20]:
        print(f"FAILED: {failure['file']}: {failure['error']}")
    if len(result["failures"]) > 20:
        print(f"...and {len(result['failures']) - 20} more failures.")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
