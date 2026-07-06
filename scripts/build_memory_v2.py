#!/usr/bin/env python3
from __future__ import annotations

import sys

from jamesos.services.memory_v2 import build_memory_v2


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    limit = 6
    if argv:
        try:
            limit = int(argv[0])
        except Exception:
            pass
    print("Building Memory V2...")
    res = build_memory_v2(limit_per_entity=limit)
    print("Done:", res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
