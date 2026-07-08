#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jamesos.services import workflow_manager


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a ComfyUI API prompt workflow without contacting ComfyUI.")
    parser.add_argument("workflow", help="Path to workflow JSON")
    args = parser.parse_args()

    path = Path(args.workflow).expanduser()
    if not path.exists():
        print(json.dumps({
            "status": "error",
            "error_code": "workflow_file_missing",
            "workflow_path": str(path),
            "message": "Workflow file does not exist.",
        }, indent=2, sort_keys=True))
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "status": "error",
            "error_code": "workflow_file_not_json",
            "workflow_path": str(path),
            "message": str(exc),
        }, indent=2, sort_keys=True))
        return 1

    structure = workflow_manager.validate_comfyui_api_prompt_structure(data)
    result = {
        "status": "ok" if structure.get("valid") else "error",
        "workflow_path": str(path),
        "workflow_format": workflow_manager.classify_workflow_format(path),
        **structure,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if structure.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
