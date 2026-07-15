#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from jamesos.services.error_handler import cli_error, handle_error
from jamesos.services.product_orchestrator import MODE, ProductOrchestrator


def _main() -> int:
    parser = argparse.ArgumentParser(description="Create or resume a draft-only product from one prompt.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create"); create.add_argument("--prompt", required=True); create.add_argument("--source-job-id")
    create.add_argument("--shop-id", type=int, required=True); create.add_argument("--mode", default=MODE, choices=(MODE,))
    create.add_argument("--price", type=float); create.add_argument("--garment-color", action="append"); create.add_argument("--size", action="append")
    create.add_argument("--confirm-printify-draft", action="store_true")
    resume = commands.add_parser("resume"); resume.add_argument("--job-id", required=True); resume.add_argument("--confirm-printify-draft", action="store_true")
    status = commands.add_parser("status"); status.add_argument("--job-id", required=True)
    report = commands.add_parser("report"); report.add_argument("--job-id", required=True)
    args = parser.parse_args(); orchestrator = ProductOrchestrator()
    if args.command == "create":
        state = orchestrator.create(prompt=args.prompt, source_job_id=args.source_job_id, shop_id=args.shop_id, mode=args.mode,
            price=round(args.price * 100) if args.price is not None else None, garment_colors=args.garment_color, sizes=args.size,
            confirm_printify_draft=args.confirm_printify_draft)
    elif args.command == "resume": state = orchestrator.resume(args.job_id, confirm_printify_draft=args.confirm_printify_draft)
    elif args.command == "status": state = orchestrator.load(args.job_id)
    else:
        path = orchestrator.report(args.job_id); print(json.dumps({"result":"report_ready","job_id":args.job_id,"report_path":str(path)},indent=2)); return 0
    result = {"result":"failed" if state["stage"]=="failed" else "ok", "job_id":state["job_id"], "stage":state["stage"],
              "publish_status":state["publish_status"], "order_status":state["order_status"], "last_error":state.get("last_error"),
              "report_path":str(orchestrator._path(state["job_id"]).with_name("product-orchestration-report.html"))}
    if state.get("last_error"): result.update(state["last_error"])
    print(json.dumps(result,indent=2)); return 1 if state["stage"]=="failed" else 0


def main() -> int:
    try: return _main()
    except Exception as exc:
        envelope=handle_error(exc,operation="product_from_prompt_cli");print(json.dumps(cli_error(envelope),indent=2));return 1


if __name__ == "__main__": raise SystemExit(main())
