#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jamesos.services.upscale_validator import validate_upscale_model_for_job


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one confirmed configurable upscale-model validation pass through local ComfyUI.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--upscale-model-name", default=None, help="Configured model name; defaults to the registry default.")
    parser.add_argument("--bleed-iterations", type=int, default=None, help="Override the selected model's preferred setting.")
    parser.add_argument("--alpha-threshold", type=int, default=None, help="Override the selected model's preferred setting.")
    parser.add_argument("--alpha-resize-method", choices=("nearest-exact", "lanczos"), default=None, help="Override the selected model's preferred setting.")
    parser.add_argument("--confirm", action="store_true", help="Required acknowledgement that this queues one local validation pass.")
    args = parser.parse_args()
    try:
        result = validate_upscale_model_for_job(
            args.job_id,
            upscale_model_name=args.upscale_model_name,
            confirmed=args.confirm,
            bleed_iterations=args.bleed_iterations,
            alpha_threshold=args.alpha_threshold,
            alpha_resize_method=args.alpha_resize_method,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
