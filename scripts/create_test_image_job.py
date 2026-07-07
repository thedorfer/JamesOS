#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jamesos.services.image_worker import create_test_image_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one approval-gated local ComfyUI test image job. Does not execute.")
    parser.add_argument("--positive-prompt", default="UnityStitches inclusive pride standalone print design, flat centered print artwork, no person, no mockup, clean bold typography, print-ready graphic")
    parser.add_argument("--negative-prompt", default="copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, blurry, misspelled text, person, human, model, wearing, product photo, lifestyle photo, room, mannequin, face, hands, body, portrait, mockup")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--brand-id", default="unitystitches")
    parser.add_argument("--draft-path", default="")
    args = parser.parse_args()

    result = create_test_image_job(
        positive_prompt=args.positive_prompt,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        width=args.width,
        height=args.height,
        brand_id=args.brand_id,
        draft_path=args.draft_path,
    )
    job = result.get("job", {})
    payload = job.get("payload", {})
    job_id = job.get("job_id", "JOB_ID")
    output_folder = f"~/JamesOSData/JamesOS/CreativeStudio/Generated/YYYY-MM-DD/{job_id}/"
    selected_provider = payload.get("pod_provider") or payload.get("image_plan", {}).get("pod_provider") or "printify"
    selected_assets = payload.get("selected_assets") or payload.get("image_plan", {}).get("selected_assets") or []
    result["selected_provider"] = selected_provider
    result["selected_assets"] = selected_assets
    result["next_commands"] = {
        "approve_cli": f"python3 scripts/job_queue.py approve {job_id}",
        "approve_api": f"curl -X POST -H \"X-JamesOS-Key: $JAMESOS_API_KEY\" http://localhost:8787/jobs/{job_id}/approve",
        "execute_approved": f"curl -X POST -H \"X-JamesOS-Key: $JAMESOS_API_KEY\" http://localhost:8787/image-worker/jobs/{job_id}/execute-approved",
        "output_folder": output_folder,
        "open_output_folder": f"xdg-open {output_folder}",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
