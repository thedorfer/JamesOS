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
from jamesos.services.image_worker import GENERATED_ROOT, create_test_image_job
from jamesos.services.job_queue import JobQueueError


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one approval-gated local ComfyUI test image job. Does not execute.")
    parser.add_argument("--positive-prompt", default="")
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--brand-id", default="commerce_shop")
    parser.add_argument("--draft-path", default="")
    parser.add_argument("--quality", choices=["draft", "production", "premium"], default="production")
    parser.add_argument("--transparent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--provider", default="printify")
    args = parser.parse_args()

    requested_workflow_type = "transparent_print_design_basic" if args.transparent else "print_design_basic"
    workflow = workflow_manager.get_executable_workflow_template(requested_workflow_type)
    try:
        result = create_test_image_job(
            positive_prompt=args.positive_prompt,
            negative_prompt=args.negative_prompt,
            seed=args.seed,
            width=args.width,
            height=args.height,
            brand_id=args.brand_id,
            draft_path=args.draft_path,
            quality=args.quality,
            transparent=args.transparent,
            provider=args.provider,
        )
    except JobQueueError as exc:
        print(json.dumps({
            "status": "error",
            "error_code": "workflow_model_checkpoint_missing",
            "message": str(exc),
            "requested_workflow_type": requested_workflow_type,
            "workflow_template_used": workflow.get("workflow_path") or workflow.get("path"),
            "comfyui_open_workflow_ignored": True,
            "note": "ComfyUI open workflow is ignored.",
            "next_step": "Put a checkpoint in ComfyUI models/checkpoints, run the model scan, then rerun this helper.",
            "create_command": "python3 scripts/create_test_image_job.py",
        }, indent=2, sort_keys=True))
        return
    job = result.get("job", {})
    payload = job.get("payload", {})
    job_id = job.get("job_id", "JOB_ID")
    output_folder = f"{GENERATED_ROOT}/YYYY-MM-DD/{job_id}/"
    selected_provider = payload.get("pod_provider") or payload.get("image_plan", {}).get("pod_provider") or "printify"
    selected_assets = payload.get("selected_assets") or payload.get("image_plan", {}).get("selected_assets") or []
    artifact = payload.get("design_artifact") or payload.get("image_plan", {}).get("design_artifact") or {}
    result["selected_provider"] = selected_provider
    result["selected_assets"] = selected_assets
    result["requested_workflow_type"] = requested_workflow_type
    result["workflow_template_used"] = workflow.get("workflow_path") or workflow.get("path")
    result["comfyui_open_workflow_ignored"] = True
    result["final_print_ready"] = bool(artifact.get("final_print_ready", False))
    result["production_candidate"] = artifact.get("quality_stage") == "production_candidate"
    result["background_removal_required"] = bool(artifact.get("background_removal_required", False))
    result["transparent_background_requested"] = bool(artifact.get("transparent_background_requested", False))
    result["manual_upload_ready"] = bool(artifact.get("manual_upload_ready", False))
    result["note"] = "ComfyUI open workflow is ignored."
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
