#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jamesos.services.design_critic import critique_design_plan, save_critique


def main() -> None:
    parser = argparse.ArgumentParser(description="Critique a local design_plan.json file.")
    parser.add_argument("design_plan_json")
    parser.add_argument("--save", action="store_true", help="Save the critique under JamesOSData.")
    args = parser.parse_args()

    plan = json.loads(Path(args.design_plan_json).expanduser().read_text(encoding="utf-8"))
    critique = critique_design_plan(plan)
    if args.save:
        result = save_critique(critique)
        critique = {**critique, "saved_path": result["path"]}
    print(json.dumps(critique, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
