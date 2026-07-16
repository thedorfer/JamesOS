#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from jamesos.services.error_handler import cli_error, handle_error
from jamesos.services.product_orchestrator import MODE, ProductOrchestrator
from jamesos.agents import CommerceAgent,EtsyAgent,PrintifyAgent
from jamesos.core.agents import AgentRegistry,AgentRunner
from jamesos.core.agents.approvals import ApprovalPolicy
from jamesos.core.agents.capabilities import ToolBroker
from jamesos.core.agents.ledger import RunLedger
from jamesos.core.agents.models import AgentRequest,ApprovalRequirement,RiskLevel,serializable
from jamesos.core.agents.secrets import SecretProvider
from jamesos.integrations.etsy_client import EtsyClient
from jamesos.integrations import etsy_oauth
from jamesos.config import VAULT

def agent_runtime(orchestrator=None,ledger=None):
    secrets=SecretProvider({"etsy.unitystitches.app":VAULT/"JamesOS"/"Secrets"/"etsy-app.json","etsy.unitystitches.oauth":VAULT/"JamesOS"/"Secrets"/"etsy-oauth.json",
        "etsy.unitystitches.oauth_pending":VAULT/"JamesOS"/"Secrets"/"etsy-oauth-pending.json"})
    def etsy_client(oauth):
        if not etsy_oauth.status()["ready_for_etsy_write"]:etsy_oauth.refresh()
        return EtsyClient({**secrets.resolve("etsy.unitystitches.app"),**secrets.resolve("etsy.unitystitches.oauth")})
    broker=ToolBroker(secrets);broker.register("etsy.client",etsy_client,"etsy.unitystitches.oauth")
    broker.register("printify.orchestrator",lambda _secret:orchestrator or ProductOrchestrator())
    registry=AgentRegistry()
    for agent in (CommerceAgent(),PrintifyAgent(),EtsyAgent()):registry.register(agent)
    return AgentRunner(registry,ledger or RunLedger(),ApprovalPolicy(),broker)

def run_agent_command(orchestrator,job_id,capability,confirmed,combined=False):
    state=orchestrator.load(job_id);listing=(state.get("evidence",{}).get("etsy_channel_test") or {}).get("etsy_listing_id")
    if not listing:raise ValueError("Recorded Etsy listing ID is required")
    run_id=f"agent-run-{uuid4().hex[:12]}";scope="publish-and-deactivate" if combined else "etsy-deactivation"
    request=AgentRequest(task_id=f"task-{uuid4().hex[:12]}",run_id=run_id,workflow_id="printify-to-etsy-inactive-review",requested_capability=capability,
        requesting_agent_id="cli",target_resources={"job_id":job_id,"listing_id":listing,"product_id":state.get("evidence",{}).get("draft",{}).get("printify_product_id")},
        input_payload={"job_id":job_id,"dry_run":not confirmed,"expected_title":"Love Is Love Rainbow Heart Shirt: LGBTQ+ Pride Unisex Tee, Inclusive Gift"},
        risk_level=RiskLevel.PUBLICATION if combined and confirmed else RiskLevel.REMOTE_WRITE if confirmed else RiskLevel.READ,
        approval_requirement=ApprovalRequirement(confirmed,scope),idempotency_key=f"{job_id}:{capability}",attempt_limit=1)
    result=agent_runtime(orchestrator).run(request,f"approved:{scope}" if confirmed else None);public=result["execution"].public_output
    agent_id="commerce" if combined else "etsy"
    return {**public,"agent_run_id":run_id,"agent_id":agent_id}


def response_summary(state: dict, orchestrator: ProductOrchestrator) -> dict:
    result = {"result":"failed" if state["stage"]=="failed" else "ok", "job_id":state["job_id"], "stage":state["stage"],
        "publish_status":state["publish_status"], "order_status":state["order_status"],
        "report_path":str(orchestrator._path(state["job_id"]).with_name("product-orchestration-report.html"))}
    if state["stage"] == "failed" and state.get("last_error"):
        result["last_error"] = state["last_error"]; result.update(state["last_error"])
    else:
        result["recovered_from_error_ids"] = [item["error_id"] for item in state.get("recovered_errors") or [] if item.get("error_id")]
    return result


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
    reconcile = commands.add_parser("reconcile-draft"); reconcile.add_argument("--job-id", required=True)
    reconcile.add_argument("--confirm-printify-draft-update", action="store_true")
    review = commands.add_parser("review-draft"); review.add_argument("--job-id", required=True)
    recover = commands.add_parser("recover-draft"); recover.add_argument("--job-id", required=True)
    recover.add_argument("--confirm-printify-draft-recovery", action="store_true")
    prepare = commands.add_parser("prepare-listing"); prepare.add_argument("--job-id", required=True)
    prepare.add_argument("--confirm-printify-listing-update", action="store_true")
    etsy = commands.add_parser("send-to-etsy-review"); etsy.add_argument("--job-id", required=True)
    etsy.add_argument("--confirm-etsy-channel-test", action="store_true")
    deactivate = commands.add_parser("deactivate-etsy-listing"); deactivate.add_argument("--job-id",required=True);deactivate.add_argument("--confirm-etsy-deactivation",action="store_true")
    inactive = commands.add_parser("send-to-etsy-inactive-review"); inactive.add_argument("--job-id",required=True);inactive.add_argument("--confirm-publish-and-deactivate",action="store_true")
    args = parser.parse_args(); orchestrator = ProductOrchestrator()
    if args.command == "create":
        state = orchestrator.create(prompt=args.prompt, source_job_id=args.source_job_id, shop_id=args.shop_id, mode=args.mode,
            price=round(args.price * 100) if args.price is not None else None, garment_colors=args.garment_color, sizes=args.size,
            confirm_printify_draft=args.confirm_printify_draft)
    elif args.command == "resume": state = orchestrator.resume(args.job_id, confirm_printify_draft=args.confirm_printify_draft)
    elif args.command == "status": state = orchestrator.load(args.job_id)
    elif args.command == "reconcile-draft":
        result=orchestrator.reconcile_draft(args.job_id,confirmed=args.confirm_printify_draft_update);print(json.dumps(result,indent=2));return 0
    elif args.command == "review-draft":
        result=orchestrator.review_draft(args.job_id);print(json.dumps(result,indent=2));return 0
    elif args.command == "recover-draft":
        result=orchestrator.recover_draft(args.job_id,confirmed=args.confirm_printify_draft_recovery);print(json.dumps(result,indent=2));return 0
    elif args.command == "prepare-listing":
        result=orchestrator.prepare_listing(args.job_id,confirmed=args.confirm_printify_listing_update);print(json.dumps(result,indent=2));return 0
    elif args.command == "send-to-etsy-review":
        result=orchestrator.send_to_etsy_review(args.job_id,confirmed=args.confirm_etsy_channel_test);print(json.dumps(result,indent=2));return 0
    elif args.command == "deactivate-etsy-listing":
        result=run_agent_command(orchestrator,args.job_id,"marketplace.listing.deactivate",args.confirm_etsy_deactivation);print(json.dumps(result,indent=2));return 0
    elif args.command == "send-to-etsy-inactive-review":
        result=run_agent_command(orchestrator,args.job_id,"commerce.workflow.publish_to_inactive_review",args.confirm_publish_and_deactivate,combined=True);print(json.dumps(result,indent=2));return 0
    else:
        path = orchestrator.report(args.job_id); print(json.dumps({"result":"report_ready","job_id":args.job_id,"report_path":str(path)},indent=2)); return 0
    result = response_summary(state, orchestrator)
    print(json.dumps(result,indent=2)); return 1 if state["stage"]=="failed" else 0


def main() -> int:
    try: return _main()
    except Exception as exc:
        envelope=handle_error(exc,operation="product_from_prompt_cli");print(json.dumps(cli_error(envelope),indent=2));return 1


if __name__ == "__main__": raise SystemExit(main())
