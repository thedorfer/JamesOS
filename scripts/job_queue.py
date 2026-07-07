from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jamesos.services.job_queue import (
    append_job_log,
    approve_job,
    create_job,
    fail_job,
    get_job,
    list_jobs,
    mark_step,
    update_job_status,
    write_job_queue_report,
)


def _payload(value: str) -> dict:
    if not value:
        return {}
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="JamesOS job queue")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("type")
    create.add_argument("--payload", default="{}")
    create.add_argument("--priority", type=int, default=5)
    create.add_argument("--no-approval", action="store_true")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--status")

    show = sub.add_parser("show")
    show.add_argument("job_id")

    status = sub.add_parser("status")
    status.add_argument("job_id")
    status.add_argument("status")

    approve = sub.add_parser("approve")
    approve.add_argument("job_id")
    approve.add_argument("--by", default="James")

    fail = sub.add_parser("fail")
    fail.add_argument("job_id")
    fail.add_argument("--reason", default="")

    log = sub.add_parser("log")
    log.add_argument("job_id")
    log.add_argument("message")

    step = sub.add_parser("step")
    step.add_argument("job_id")
    step.add_argument("name")
    step.add_argument("status")
    step.add_argument("--note", default="")

    sub.add_parser("report")

    args = parser.parse_args()

    if args.command == "create":
        result = create_job(
            args.type,
            _payload(args.payload),
            priority=args.priority,
            requires_approval=not args.no_approval,
        )
    elif args.command == "list":
        result = list_jobs(args.status)
    elif args.command == "show":
        result = get_job(args.job_id)
    elif args.command == "status":
        result = update_job_status(args.job_id, args.status)
    elif args.command == "approve":
        result = approve_job(args.job_id, args.by)
    elif args.command == "fail":
        result = fail_job(args.job_id, args.reason)
    elif args.command == "log":
        result = append_job_log(args.job_id, args.message)
    elif args.command == "step":
        result = mark_step(args.job_id, args.name, args.status, args.note)
    else:
        result = {"report": write_job_queue_report()}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
