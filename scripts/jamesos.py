#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services.commerce_preparation import UnifiedCommercePreparation
from jamesos.services.commerce_binding_migration import LegacyCommerceBindingMigration
from jamesos.services.commerce_publication import CommercePublicationExecutor,EtsyMarketplaceAdapter,PrintifyProviderDraftAdapter
from jamesos.services.commerce_revision import CommerceRevisionService
from jamesos.services.commerce_creation import CommerceCreationService
from jamesos.core.profiles.selection import list_commerce_profiles
from jamesos.core.agents.secrets import SecretProvider
from jamesos.core.profiles.selection import load_commerce_profile
from jamesos.integrations.etsy_client import EtsyClient
from jamesos.config import VAULT
from jamesos.services.error_handler import cli_error,handle_error
from jamesos.services.scheduler import SchedulerService


def _main(workflow: CommerceWorkflow | None = None, scheduler: SchedulerService | None = None) -> int:
    parser=argparse.ArgumentParser(prog="jamesos")
    domains=parser.add_subparsers(dest="domain",required=True);commerce=domains.add_parser("commerce")
    commands=commerce.add_subparsers(dest="command",required=True)
    for name in ("prepare","status","review"):
        command=commands.add_parser(name);command.add_argument("--job-id",required=True)
        if name=="review":command.add_argument("--open",action="store_true")
    for name in ("approve","request-changes"):
        command=commands.add_parser(name);command.add_argument("--job-id",required=True);command.add_argument("--proposal-sha256",required=True)
        command.add_argument("--confirm",action="store_true")
        if name=="request-changes":command.add_argument("--note",default="")
    create_commerce=commands.add_parser("create");create_commerce.add_argument("--prompt");create_commerce.add_argument("--price-cents",type=int)
    create_commerce.add_argument("--color",action="append");create_commerce.add_argument("--size",action="append");create_commerce.add_argument("--profile-id")
    create_commerce.add_argument("--resume-job-id");create_commerce.add_argument("--authorize-draft-work",action="store_true");create_commerce.add_argument("--open",action="store_true")
    create_commerce.add_argument("--profile");create_commerce.add_argument("--brief");create_commerce.add_argument("--brief-file");create_commerce.add_argument("--exact-phrase");create_commerce.add_argument("--listing-title");create_commerce.add_argument("--special-instructions");create_commerce.add_argument("--no-run",action="store_true");create_commerce.add_argument("--confirm-destination",action="store_true")
    for name in ("publish","reconcile-publication"):
        command=commands.add_parser(name);command.add_argument("--job-id",required=True);command.add_argument("--proposal-sha256",required=True)
        if name=="publish":command.add_argument("--confirm",action="store_true")
    migrate=commands.add_parser("migrate-execution-binding");migrate.add_argument("--job-id",required=True);migrate.add_argument("--profile-id")
    migrate.add_argument("--confirm",action="store_true");migrate.add_argument("--set-selected-profile",action="store_true");migrate.add_argument("--repair-profile-binding",action="store_true")
    resume_revision=commands.add_parser("resume-revision");resume_revision.add_argument("--job-id",required=True);resume_revision.add_argument("--open",action="store_true")
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
        service=workflow or CommerceWorkflow()
        if args.command=="approve":result=service.approve(args.job_id,args.proposal_sha256,confirmed=args.confirm)
        elif args.command=="request-changes":result=service.request_changes(args.job_id,args.proposal_sha256,note=args.note,confirmed=args.confirm)
        elif args.command=="create":
            if args.profile or args.brief or args.brief_file:
                profile_id=args.profile
                if not profile_id:
                    if not sys.stdin.isatty():raise ValueError("--profile is required in noninteractive mode")
                    profiles=list_commerce_profiles();
                    for index,item in enumerate(profiles,1):
                        config=item.get("configuration") or {};print(f"{index}. {item.get('display_name') or item.get('profile_id')}\n   Printify {config.get('printify_shop_id')} → Etsy {config.get('etsy_shop_slug')}\n")
                    profile_id=profiles[int(input("Selection: "))-1]["profile_id"]
                brief=args.brief or (Path(args.brief_file).read_text(encoding="utf-8") if args.brief_file else "")
                confirmed=args.confirm_destination
                profile=next((item for item in list_commerce_profiles(False) if item.get("profile_id")==profile_id),None);config=(profile or {}).get("configuration") or {}
                if sys.stdin.isatty() and not confirmed:
                    print(f"Brand: {(profile or {}).get('display_name')}\nProfile: {profile_id}\nPrintify: {config.get('printify_shop_title')} — {config.get('printify_shop_id')}\nEtsy: {config.get('etsy_shop_slug')}\nStatus: GENERATION QUEUED / NOT PUBLISHED")
                    confirmed=input("Continue? [y/N] ").strip().casefold() in {"y","yes"}
                if not confirmed:raise ValueError("Explicit destination confirmation is required")
                creation=CommerceCreationService(service);result=creation.create_job(commerce_profile_id=profile_id,product_brief=brief,exact_phrase=args.exact_phrase or "",listing_title=args.listing_title or "",special_instructions=args.special_instructions or "",destination_confirmed=True)
                loading_url=f"http://127.0.0.1:8787/commerce/jobs/{result['job_id']}/loading"
                if args.open:webbrowser.open(loading_url)
                if not args.no_run:result=creation.run_generation(result["job_id"])
                result={**result,"loading_url":loading_url}
            else:
                preparation=UnifiedCommercePreparation(service.orchestrator,workflow=service)
                result=preparation.create(prompt=args.prompt,price_cents=args.price_cents,colors=args.color,sizes=args.size,profile_id=args.profile_id,
                    resume_job_id=args.resume_job_id,authorize_draft_work=args.authorize_draft_work)
                if args.open and result.get("review_url"):webbrowser.open(result["review_url"])
        elif args.command in {"publish","reconcile-publication"}:
            if args.command=="publish" and not args.confirm:
                result=CommercePublicationExecutor(service).execute(job_id=args.job_id,proposal_sha256=args.proposal_sha256,confirmed=False)
            else:
                profile=load_commerce_profile(required=True);config=profile.get("configuration") or {};client=service.orchestrator.adapters.client_factory()
                secrets=SecretProvider({"etsy.app":VAULT/"JamesOS"/"Secrets"/"etsy-app.json","etsy.oauth":VAULT/"JamesOS"/"Secrets"/"etsy-oauth.json"})
                etsy=EtsyClient({**secrets.resolve("etsy.app"),**secrets.resolve("etsy.oauth")})
                executor=CommercePublicationExecutor(service,provider=PrintifyProviderDraftAdapter(client),
                    marketplace=EtsyMarketplaceAdapter(etsy,config.get("etsy_shop_id")),profile_loader=load_commerce_profile)
                result=(executor.execute(job_id=args.job_id,proposal_sha256=args.proposal_sha256,confirmed=True) if args.command=="publish"
                    else executor.reconcile(job_id=args.job_id,proposal_sha256=args.proposal_sha256))
        elif args.command=="migrate-execution-binding":
            result=LegacyCommerceBindingMigration(service).migrate(job_id=args.job_id,profile_id=args.profile_id,confirmed=args.confirm,
                set_selected_profile=args.set_selected_profile,repair_profile_binding=args.repair_profile_binding)
        elif args.command=="resume-revision":
            result=CommerceRevisionService(service).resume(args.job_id)
            if args.open and result.get("review_url"):webbrowser.open(result["review_url"])
        else:
            result=getattr(service,args.command)(args.job_id)
            if args.command=="review" and args.open:webbrowser.open(result["review_url"])
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
