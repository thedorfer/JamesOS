#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services.error_handler import cli_error,handle_error
from jamesos.services.scheduler import SchedulerService


def _main(workflow: CommerceWorkflow | None = None, scheduler: SchedulerService | None = None) -> int:
    parser=argparse.ArgumentParser(prog="jamesos")
    domains=parser.add_subparsers(dest="domain",required=True);commerce=domains.add_parser("commerce")
    commands=commerce.add_subparsers(dest="command",required=True)
    for name in ("prepare","status","review"):
        command=commands.add_parser(name);command.add_argument("--job-id",required=True)
    schedule=domains.add_parser("schedule");schedule_commands=schedule.add_subparsers(dest="command",required=True)
    create=schedule_commands.add_parser("create");create.add_argument("--name",required=True);create.add_argument("--timezone",required=True)
    triggers=create.add_mutually_exclusive_group(required=True);triggers.add_argument("--once-at");triggers.add_argument("--every-hours",type=int)
    triggers.add_argument("--daily-at");triggers.add_argument("--weekly-at")
    create.add_argument("--anchor-at");create.add_argument("--weekday",action="append");create.add_argument("--job-template-file",required=True)
    create.add_argument("--misfire-policy",choices=("skip","fire_once"),default="fire_once");create.add_argument("--misfire-grace-seconds",type=int,default=3600)
    create.add_argument("--confirm-create",action="store_true")
    schedule_commands.add_parser("list")
    for name in ("show","preview","enable","disable"):
        command=schedule_commands.add_parser(name);command.add_argument("--schedule-id",required=True)
        if name=="preview":command.add_argument("--count",type=int,default=5)
        if name in {"enable","disable"}:command.add_argument("--confirm",action="store_true")
    tick=schedule_commands.add_parser("tick");tick.add_argument("--confirm-enqueue",action="store_true")
    args=parser.parse_args()
    if args.domain=="commerce":
        service=workflow or CommerceWorkflow();result=getattr(service,args.command)(args.job_id)
    else:
        service=scheduler or SchedulerService()
        if args.command=="create":
            path=Path(args.job_template_file)
            if not path.is_file():raise ValueError("job template file was not found")
            template=json.loads(path.read_text(encoding="utf-8"))
            if args.once_at:trigger={"type":"once","at":args.once_at}
            elif args.every_hours is not None:
                if not args.anchor_at:raise ValueError("--anchor-at is required with --every-hours")
                trigger={"type":"hourly","every_hours":args.every_hours,"anchor_at":args.anchor_at}
            elif args.daily_at:trigger={"type":"daily","local_time":args.daily_at}
            else:
                if not args.weekday:raise ValueError("--weekday is required with --weekly-at")
                trigger={"type":"weekly","weekdays":args.weekday,"local_time":args.weekly_at}
            result=service.create(name=args.name,timezone_name=args.timezone,trigger=trigger,job_template=template,
                misfire_policy=args.misfire_policy,misfire_grace_seconds=args.misfire_grace_seconds,confirmed=args.confirm_create)
        elif args.command=="list":result=service.list_schedules()
        elif args.command=="show":result=service.show(args.schedule_id)
        elif args.command=="preview":result=service.preview_occurrences(args.schedule_id,args.count)
        elif args.command=="tick":result=service.tick(confirmed=args.confirm_enqueue)
        elif args.command=="enable":result=service.enable(args.schedule_id,confirmed=args.confirm)
        else:result=service.disable(args.schedule_id,confirmed=args.confirm)
    print(json.dumps(result,indent=2));return 0


def main() -> int:
    try:return _main()
    except Exception as exc:
        envelope=handle_error(exc,operation="jamesos.cli",persist=False,log=False)
        print(json.dumps(cli_error(envelope),indent=2));return 1


if __name__=="__main__":raise SystemExit(main())
