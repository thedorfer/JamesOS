import json
import hmac
import ipaddress
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File,BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from jamesos.config import VAULT
from jamesos.core.errors import JamesOSError, StateConflictError
from jamesos.services.error_handler import api_error, handle_error
from jamesos.core.queue import enqueue_job
from jamesos.services.search_service import search_notes_index
from jamesos.services.status_report import generate_status_report
from jamesos.services.briefing import generate_daily_briefing
from jamesos.services.brand_registry import (
    brand_health,
    get_brand,
    get_default_brand,
    list_brands,
    validate_brand_product_niche,
)
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.rich_context import build_rich_context
from jamesos.services.agent import ask_agent, handle_jade_message
from jamesos.services.jade_planner import answer_with_planner
from jamesos.services.jade_brain import answer_with_brain, summarize_chat_history
from jamesos.services.jade_reasoner import answer_with_reasoner
from jamesos.services.jade_context_packages import dashboard_cards
from jamesos.services.job_queue import (
    JobQueueError,
    approve_job,
    create_job,
    fail_job,
    get_job,
    list_jobs,
)
from jamesos.services.knowledge_graph import build_knowledge_graph, edit_capabilities, graph_lookup
from jamesos.services.memory_service import remember, search_memory
from jamesos.services.typed_index import build_typed_indexes, search_typed_indexes
from jamesos.services.tool_router import route_tool
from jamesos.services.attachment_ingest import ingest_attachments
from jamesos.services.attachment_processor import process_pending_attachment_jobs
from jamesos.services.asset_library import scan_assets
from jamesos.services.file_intelligence import build_file_knowledge
from jamesos.services.phone_ingest import ingest_phone_event, ingest_phone_events, phone_daily_summary
from jamesos.services.phone_ingestion import health as phone_ingestion_health, methods as phone_ingestion_methods
from jamesos.services.creative_studio import (
    approve_creative_job,
    create_creative_job,
    create_pipeline,
    fail_creative_job,
    get_creative_job,
    get_pipeline,
    health as creative_studio_health,
    list_creative_jobs,
    list_pipelines,
)
from jamesos.services.control_center import (
    control_center as control_center_summary,
    human_summary as control_center_human_summary,
    health as control_center_health,
    integrations as control_center_integrations,
    jobs as control_center_jobs,
    services as control_center_services,
    storage as control_center_storage,
)
from jamesos.services.comfyui_client import health as comfyui_health
from jamesos.services.design_critic import (
    critique_design_plan,
    critique_generated_artifact,
    design_critic_health,
    load_critique,
    save_critique,
)
from jamesos.services.design_planner import (
    create_design_plan,
    design_plan_health,
    load_design_plan,
)
from jamesos.services.design_variation_service import (
    create_design_run,
    get_design_run,
    list_design_runs,
    promote_best,
    score_design_run,
)
from jamesos.services.image_finisher import approve_concept_for_job, prepare_transparent_artifact_for_job
from jamesos.services.upscale_model_registry import list_upscale_models
from jamesos.services.upscale_validator import validate_upscale_model_for_job
from jamesos.services.production_artifact import (
    approve_production_artifact_for_job,
    approve_transparent_artifact_for_job,
    prepare_production_artifact_for_job,
)
from jamesos.integrations.printify_client import PrintifyClient, PrintifyAPIError
from jamesos.services import printify_product
from jamesos.services.image_worker import (
    analyze_output_image_for_job,
    comfy_response_for_job,
    create_test_image_job,
    execute_approved_image_job,
    health as image_worker_health,
    plan as image_worker_plan,
    prepared_workflow_for_job,
)
from jamesos.services.model_registry import get_model, list_models, scan_and_report as scan_models_and_report
from jamesos.services.planner import create_plan, health as planner_health
from jamesos.services.pod_provider_registry import get_provider, list_providers, provider_health
from jamesos.services.prompt_library import get_prompt_template, load_prompt_templates
from jamesos.services.recipe_library import get_recipe, list_recipes, recipes_by_product
from jamesos.services.server_config import (
    integration_health,
    server_config,
    service_health,
    write_server_config_report,
)
from jamesos.services.style_registry import get_style, list_styles
from jamesos.services.commerce_product_pipeline import (
    drafts_for_date as commerce_shop_drafts_for_date,
    generate_daily_product_drafts as generate_commerce_shop_daily_drafts,
    health as commerce_shop_health,
    list_drafts as list_commerce_shop_drafts,
)
from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services import product_orchestrator
from jamesos.services.commerce_publication import CommercePublicationExecutor,EtsyMarketplaceAdapter,PrintifyProviderDraftAdapter,ConnectedSalesChannelMarketplaceAdapter
from jamesos.services.commerce_revision import CommerceRevisionService
from jamesos.services.commerce_creation import CommerceCreationService
from jamesos.core.agents.secrets import SecretProvider
from jamesos.core.profiles.selection import load_commerce_profile,list_commerce_profiles,load_commerce_profile_by_id
from jamesos.integrations.etsy_client import EtsyClient
from jamesos.services.worker_registry import get_worker, list_workers
from jamesos.services.workflow_manager import get_workflow, list_workflows, scan_and_report as scan_workflows_and_report
from jamesos.core.agency.routes import router as agency_router

API_KEY_FILE = VAULT / "JamesOS" / "Secrets" / "api_key.txt"
CHAT_HISTORY_FILE = VAULT / "JamesOS" / "Memory" / "chat_history.json"

app = FastAPI(title="JamesOS API")
_COMMERCE_CREATE_CSRF=__import__("secrets").token_urlsafe(32)
# This project's FastAPI compatibility layer represents include_router() as a
# sentinel in app.routes. Register the already-prefixed APIRoutes directly so
# existing route audits continue to see ordinary path-bearing route objects.
app.router.routes.extend(agency_router.routes)


@app.exception_handler(JamesOSError)
async def jamesos_error_response(request: Request, exc: JamesOSError):
    envelope = handle_error(exc, operation=exc.operation, request_id=request.headers.get("x-request-id"))
    status, body = api_error(envelope)
    return JSONResponse(status_code=status, content=body)


def _printify_client() -> PrintifyClient:
    return PrintifyClient()


class IntakeRequest(BaseModel):
    title: str
    content: str
    source: str = "api"
    source_detail: str = ""


class AskRequest(BaseModel):
    question: str
    use_ai: bool = True
    mode: str = "personal"


class QuickNoteRequest(BaseModel):
    text: str
    title: str = "Quick Note"


class ShareLinkRequest(BaseModel):
    url: str
    title: str = "Shared Link"
    note: str = ""


class MemoryRequest(BaseModel):
    text: str
    source: str = "api"
    importance: str = "normal"


class ToolRequest(BaseModel):
    question: str


class JobCreateRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5
    requires_approval: bool = True
    steps: list[str | dict[str, Any]] = Field(default_factory=list)


class JobFailRequest(BaseModel):
    reason: str = ""


class CreativeJobCreateRequest(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5


class CreativePipelineCreateRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = 5


class PlannerPlanRequest(BaseModel):
    intent: str = ""
    prompt: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ImageWorkerPlanRequest(BaseModel):
    package: dict[str, Any] = Field(default_factory=dict)


class DesignRunCreateRequest(BaseModel):
    brand_id: str = "commerce_shop"
    product_type: str = "womens_underwear"
    niche: str = "trans pride"
    recipe_id: str = "underwear/pride_pattern"
    variations: int = 4
    quality: str = "premium"
    provider: str = "printify"
    create_image_jobs: bool = True


class DesignPlanRequest(BaseModel):
    brand_id: str = "commerce_shop"
    product_type: str = "womens_underwear"
    niche: str = "trans pride"
    recipe_id: str = "underwear/pride_pattern"
    quality_target: int = 90


class CritiquePlanRequest(BaseModel):
    design_plan: dict[str, Any] = Field(default_factory=dict)
    artifact: dict[str, Any] = Field(default_factory=dict)


class CritiqueArtifactRequest(BaseModel):
    artifact: dict[str, Any] = Field(default_factory=dict)


class BrandValidateRequest(BaseModel):
    product_type: str
    niche: str


class TestImageJobRequest(BaseModel):
    positive_prompt: str = "Commerce Shop inclusive pride standalone print design, flat centered print artwork, no person, no mockup, clean bold typography, print-ready graphic"
    negative_prompt: str = "copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, blurry, misspelled text, person, human, model, wearing, product photo, lifestyle photo, room, mannequin, face, hands, body, portrait, mockup"
    seed: int = 1
    width: int = 768
    height: int = 768
    brand_id: str = "commerce_shop"
    draft_path: str = ""


class ConceptApprovalRequest(BaseModel):
    approved_by: str = "api_user"


class UpscaleValidationRequest(BaseModel):
    confirmed: bool = False
    upscale_model_name: str | None = None
    bleed_iterations: int | None = None
    alpha_threshold: int | None = None
    alpha_resize_method: str | None = None


class TransparentArtifactApprovalRequest(BaseModel):
    approved_by: str = "api_user"


class ProductionArtifactRequest(BaseModel):
    confirmed: bool = False
    upscale_model_name: str | None = None
    target_overrides: dict[str, Any] | None = None
    production_strategy: str = "ai_upscale"
    artwork_category: str | None = None
    strategy_selected_by: str = "api_request"


class ProductionArtifactApprovalRequest(BaseModel):
    approved_by: str
    confirmed: bool = False


class PrintifyUploadRequest(BaseModel):
    confirmed: bool = False
    image_url: str | None = None


class PrintifyCreateDraftRequest(BaseModel):
    confirmed: bool = False


class PhoneEventRequest(BaseModel):
    type: str = "notification"
    device: str = "android"
    timestamp: str = ""
    person: str = ""
    number: str = ""
    direction: str = ""
    app: str = ""
    text: str = ""
    title: str = ""
    body: str = ""
    package: str = ""
    duration: str = ""


class PhoneBatchRequest(BaseModel):
    events: list[dict[str, Any]]


def _search_query_from_question(question: str) -> str:
    q = question.strip()

    prefixes = [
        "what do you know about ",
        "tell me about ",
        "summarize ",
        "what is ",
        "who is ",
        "show me ",
        "find ",
    ]

    lower = q.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    q = q.rstrip(" ?.")
    return q or question


def _read_search_context(query: str, limit: int = 8) -> str:
    from jamesos.services.search_service import search_notes_index

    result = search_notes_index(query)
    lines = ["# Keyword Search Context", "", result, ""]

    import re
    links = re.findall(r"\[\[([^\]]+)\]\]", result)

    added = 0
    for link in links:
        if added >= limit:
            break

        target = link.split("|")[0]
        path = VAULT / f"{target}.md"

        if path.exists():
            lines.extend([
                "",
                f"## Source: [[{target}]]",
                "",
                path.read_text(encoding="utf-8", errors="ignore")[:1500],
            ])
            added += 1
    return "\n".join(lines)


def _expected_key() -> str:
    if not API_KEY_FILE.exists():
        raise HTTPException(status_code=500, detail="API key is not configured")
    return API_KEY_FILE.read_text(encoding="utf-8").strip()


def require_key(x_jamesos_key: str | None = Header(default=None)) -> None:
    if x_jamesos_key != _expected_key():
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_local(request: Request) -> None:
    try:address=ipaddress.ip_address(request.client.host if request.client else "")
    except ValueError:raise HTTPException(status_code=403,detail="Commerce review is localhost-only")
    if not address.is_loopback:raise HTTPException(status_code=403,detail="Commerce review is localhost-only")


def _browser_authenticate(workflow: CommerceWorkflow,job_id: str,cookie: str) -> None:
    try:workflow.authenticate_browser_session(job_id,cookie)
    except JamesOSError as exc:raise HTTPException(status_code=401,detail="Invalid or expired browser review session") from exc


def _validate_commerce_origin(request: Request) -> None:
    def header_values(name: str) -> list[str]:
        getlist=getattr(request.headers,"getlist",None)
        if callable(getlist):return list(getlist(name))
        value=request.headers.get(name)
        return [] if value is None else [value]

    origins=header_values("origin");hosts=header_values("host")
    if len(origins)!=1 or len(hosts)!=1:raise HTTPException(status_code=403,detail="Invalid origin")
    origin=origins[0].strip();host=hosts[0].strip()
    if not origin or origin=="null" or not host or "," in origin or "," in host:
        raise HTTPException(status_code=403,detail="Invalid origin")
    try:
        parsed=urlsplit(origin)
        parsed_host=urlsplit(f"//{host}")
        hostname=parsed.hostname;host_hostname=parsed_host.hostname
        origin_port=parsed.port;host_port=parsed_host.port
    except (TypeError,ValueError):
        raise HTTPException(status_code=403,detail="Invalid origin")
    loopback={"127.0.0.1","localhost","::1"}
    if (parsed.scheme!="http" or hostname not in loopback or host_hostname not in loopback
            or origin_port is None or host_port is None or hostname!=host_hostname or origin_port!=host_port
            or parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or parsed_host.username is not None or parsed_host.password is not None or parsed_host.path
            or parsed_host.query or parsed_host.fragment):
        raise HTTPException(status_code=403,detail="Invalid origin")


async def _commerce_form(request: Request, workflow: CommerceWorkflow, job_id: str) -> dict[str,str]:
    _require_local(request)
    _browser_authenticate(workflow,job_id,request.cookies.get("jamesos_commerce_review",""))
    if request.headers.get("content-type","").split(";",1)[0]!="application/x-www-form-urlencoded":
        raise HTTPException(status_code=415,detail="Form encoding required")
    values={key:items[-1] for key,items in parse_qs((await request.body()).decode("utf-8"),keep_blank_values=True).items()}
    try:private=json.loads((workflow.orchestrator._path(job_id).parent/"commerce-proposal"/"current-private.json").read_text())
    except (OSError,ValueError):raise HTTPException(status_code=404,detail="Proposal not found")
    token=values.get("csrf_token","")
    if not token or not hmac.compare_digest(token,str(private.get("csrf_token") or "")):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    _validate_commerce_origin(request)
    return values


def _commerce_review_page(workflow: CommerceWorkflow,job_id: str,*,active_forms: bool) -> str:
    root=workflow.orchestrator._path(job_id).parent/"commerce-proposal"
    proposal=json.loads((root/"current.json").read_text());private=json.loads((root/"current-private.json").read_text())
    page=(root/"review.html").read_text(encoding="utf-8");job_state=workflow._state(job_id);stage=job_state.get("stage");destination=job_state.get("destination") or {}
    if destination:
        panel=(f"<section id='destination-panel'><strong>ACTIVE BRAND</strong><br>{html_escape(str(job_state.get('brand_display_name') or ''))}<br><strong>PROFILE</strong><br>{html_escape(str(job_state.get('commerce_profile_id') or job_state.get('profile_id') or ''))}<br>"
            f"<strong>PRINTIFY STORE</strong><br>{html_escape(str(destination.get('printify_shop_title') or ''))} — {html_escape(str(destination.get('printify_shop_id') or ''))}<br><strong>ETSY DESTINATION</strong><br>{html_escape(str(destination.get('etsy_shop_slug') or ''))}<br>"
            f"<strong>REVISION</strong><br>{int(job_state.get('revision_number') or 0)}<br><strong>STATUS</strong><br>UNPUBLISHED<br>NO ORDER CREATED</section>")
        page=page.replace("<header>",panel+"<header>",1)
    revision_completed=(workflow._state(job_id).get("evidence") or {}).get("revision_completed")
    if stage=="awaiting_final_approval" and revision_completed:
        receipt=("<section id='revision-result' style='background:#e5f6e9;border:3px solid #18743b;padding:1.2rem;border-radius:10px;margin:1rem 0'>"
            "<h2>CHANGES APPLIED SUCCESSFULLY</h2><p><strong>NEW PROPOSAL READY FOR REVIEW</strong><br><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p></section>")
        page=page.replace("<header>",receipt+"<header>",1)
    if stage=="proposal_approved":
        page=page.replace("NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL","PROPOSAL APPROVED</strong><br><strong>NOT YET PUBLISHED</strong><br><strong>NO ORDER CREATED")
        approval=json.loads((root/"approval.json").read_text())
        digest=html_escape(str(approval["proposal_sha256"]));short=digest[:12]
        receipt=("<section id='approval-result' style='background:#e5f6e9;border:3px solid #18743b;padding:1.2rem;border-radius:10px;margin:1rem 0'>"
            f"<h2>Approval submitted successfully</h2><p><strong>Approved at:</strong> {html_escape(str(approval['approved_at']))}</p>"
            f"<p><strong>Proposal:</strong> {short}…</p><details><summary>Full proposal SHA</summary><code>{digest}</code></details>"
            "<p><strong>NOT YET PUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p></section>")
        page=page.replace("<header>",receipt+"<header>",1)
    elif stage=="revision_requested":
        page=page.replace("NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL","CHANGES REQUESTED</strong><br><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED")
        revision=json.loads((root/"revision-request.json").read_text());note=str(revision.get("note") or "")
        note_html=f"<p><strong>Submitted note:</strong> {html_escape(note)}</p>" if note else ""
        receipt=("<section id='revision-result' style='background:#e7f1ff;border:3px solid #366ca8;padding:1.2rem;border-radius:10px;margin:1rem 0'>"
            f"<h2>Changes requested successfully</h2><p><strong>Requested at:</strong> {html_escape(str(revision['requested_at']))}</p>{note_html}"
            "<p><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p></section>")
        page=page.replace("<header>",receipt+"<header>",1)
    elif stage in {"completed","final_state_verified"}:
        page=page.replace("NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL","PUBLISHED SUCCESSFULLY</strong><br><strong>FINAL STATE VERIFIED</strong><br><strong>NO ORDER CREATED")
        execution=json.loads((root/"publication-execution.json").read_text());url=execution.get("public_listing_url")
        link=f"<p><a href='{html_escape(str(url),quote=True)}'>View marketplace listing</a></p>" if url else ""
        receipt=("<section id='publication-result' style='background:#e5f6e9;border:3px solid #18743b;padding:1.2rem;border-radius:10px;margin:1rem 0'>"
            f"<h2>PUBLISHED SUCCESSFULLY</h2><p><strong>Proposal:</strong> {html_escape(str(execution['proposal_sha256']))}</p>"
            f"<p><strong>Approved at:</strong> {html_escape(str(execution.get('approved_at') or ''))}<br><strong>Publication started:</strong> {html_escape(str(execution.get('publication_started_at') or ''))}<br><strong>Completed at:</strong> {html_escape(str(execution.get('completed_at') or ''))}</p>"
            f"<p><strong>Marketplace:</strong> {html_escape(str(execution.get('marketplace') or ''))}<br><strong>Verified final state:</strong> {html_escape(str(execution.get('verified_final_state') or ''))}<br><strong>Provider update verified:</strong> yes</p>{link}<p><strong>NO ORDER CREATED</strong></p></section>")
        page=page.replace("<header>",receipt+"<header>",1)
    elif stage=="publication_uncertain":
        page=page.replace("NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL","APPROVAL SUBMITTED</strong><br><strong>PUBLICATION RESULT UNCERTAIN</strong><br><strong>NO ORDER WILL BE CREATED")
        receipt="<section id='publication-result' style='background:#fff1cf;border:3px solid #b97800;padding:1.2rem'><h2>PUBLICATION RESULT UNCERTAIN</h2><p><strong>DO NOT CLICK PUBLISH AGAIN</strong><br>RUN READ-ONLY RECONCILIATION<br>NO ORDER CREATED</p></section>"
        page=page.replace("<header>",receipt+"<header>",1)
    elif stage=="provider_update_uncertain":
        page=page.replace("<header>","<section id='publication-result' style='background:#fff1cf;border:3px solid #b97800;padding:1.2rem'><h2>PROVIDER UPDATE RESULT UNCERTAIN</h2><p><strong>DO NOT RETRY</strong><br>RUN READ-ONLY RECONCILIATION<br>NO ORDER CREATED</p></section><header>",1)
    elif stage=="marketplace_listing_pending":
        page=page.replace("<header>","<section id='publication-result' style='background:#fff1cf;border:3px solid #b97800;padding:1.2rem'><h2>PUBLICATION SUBMITTED</h2><p><strong>MARKETPLACE LISTING PENDING</strong><br>DO NOT PUBLISH AGAIN<br>RUN READ-ONLY RECONCILIATION<br>NO ORDER CREATED</p></section><header>",1)
    elif stage=="publication_failed":
        page=page.replace("<header>","<section id='publication-result'><h2>PUBLICATION NOT SUBMITTED</h2><p>Approval is retained. NO ORDER CREATED.</p></section><header>",1)
    if not active_forms or stage not in {"awaiting_final_approval","proposal_approved"}:return page
    job=html_escape(job_id,quote=True);digest=html_escape(str(proposal["proposal_sha256"]),quote=True);csrf=html_escape(str(private["csrf_token"]),quote=True)
    etsy_slug=html_escape(str(destination.get("etsy_shop_slug") or ""));label=f"Approve and Publish to {etsy_slug}" if etsy_slug else "Approve &amp; Publish"
    destination_input=f"<input type='hidden' name='destination_confirmed' value='{etsy_slug}'>" if etsy_slug else ""
    actions=(f"<section class='actions' id='browser-actions'><form method='post' action='/commerce/proposals/{job}/approve#publication-result'>"
        f"<input type='hidden' name='proposal_sha256' value='{digest}'><input type='hidden' name='csrf_token' value='{csrf}'>"
        f"{destination_input}"
        f"<button class='approve' type='submit'>{label}</button></form>"
        f"<details><summary>Request changes</summary><form method='post' action='/commerce/proposals/{job}/request-changes#revision-result'>"
        f"<input type='hidden' name='proposal_sha256' value='{digest}'><input type='hidden' name='csrf_token' value='{csrf}'>"
        "<label for='note'>Optional revision note</label><textarea id='note' name='note' maxlength='1000'></textarea>"
        "<button type='submit'>Request changes</button></form></details>"
        + (f"<form method='post' action='/commerce/proposals/{job}/cancel'><input type='hidden' name='proposal_sha256' value='{digest}'><input type='hidden' name='csrf_token' value='{csrf}'><button type='submit'>Cancel Product</button></form>" if destination else "") + "</section>")
    return page.replace("<section class='actions' id='browser-actions'><p>Open through the JamesOS localhost review URL to approve or request changes.</p></section>",actions)


def _review_response(page: str,status_code: int=200) -> HTMLResponse:
    return HTMLResponse(page,status_code=status_code,headers={"Cache-Control":"no-store","Referrer-Policy":"origin",
        "Content-Security-Policy":"default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

def _commerce_ui_response(page:str,status_code:int=200)->HTMLResponse:
    return HTMLResponse(page,status_code=status_code,headers={"Cache-Control":"no-store","Referrer-Policy":"origin",
        "Content-Security-Policy":"default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})


@app.get("/commerce/new",response_class=HTMLResponse)
def commerce_new_route(request:Request):
    _require_local(request);cards=[]
    for index,profile in enumerate(list_commerce_profiles()):
        config=profile.get("configuration") or {};pid=html_escape(str(profile.get("profile_id") or ""),quote=True);display=html_escape(str(profile.get("display_name") or pid));shop=html_escape(str(config.get("printify_shop_title") or display));slug=html_escape(str(config.get("etsy_shop_slug") or ""));shop_id=int(config["printify_shop_id"])
        cards.append(f"<label class='card'><input type='radio' name='commerce_profile_id' value='{pid}' data-destination='{slug}' {'checked' if index==0 else ''} required><strong>{display}</strong><br>Profile: {pid}<br>Printify: {shop} — {shop_id}<br>Etsy: {slug}</label>")
    page=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>New commerce product</title><style>body{font:16px system-ui;max-width:900px;margin:auto;padding:2rem}.cards{display:grid;gap:1rem}.card{border:2px solid #ccd;padding:1rem;border-radius:10px}textarea,input[type=text]{width:100%;box-sizing:border-box;margin:.4rem 0 1rem;padding:.6rem}</style>"
        f"<h1>New Commerce Product</h1><form method='post' action='/commerce/new'><input type='hidden' name='csrf_token' value='{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}'><div class='cards'>{''.join(cards)}</div>"
        "<label>Exact phrase<textarea name='exact_phrase' maxlength='500'></textarea></label><label>Product brief<textarea name='product_brief' maxlength='5000' required></textarea></label><label>Listing title<input type='text' name='listing_title' maxlength='140'></label><label>Special instructions<textarea name='special_instructions' maxlength='3000'></textarea></label>"
        "<input type='hidden' name='destination_confirmed' value='true'><button id='generate'>Generate unpublished draft</button><p id='destination'></p></form><script>const r=[...document.querySelectorAll('input[name=commerce_profile_id]')],b=document.getElementById('generate'),d=document.getElementById('destination');function u(){const x=r.find(x=>x.checked);if(x){b.textContent='Generate unpublished draft in '+x.dataset.destination;d.textContent='Destination: '+x.dataset.destination}}r.forEach(x=>x.addEventListener('change',u));u()</script>")
    return _commerce_ui_response(page)


@app.post("/commerce/new")
async def commerce_new_submit(request:Request,background_tasks:BackgroundTasks):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/x-www-form-urlencoded":raise HTTPException(status_code=415,detail="Form encoding required")
    values={key:items[-1] for key,items in parse_qs((await request.body()).decode(),keep_blank_values=True).items()}
    if not hmac.compare_digest(values.get("csrf_token",""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    service=CommerceCreationService();result=service.create_job(commerce_profile_id=values.get("commerce_profile_id",""),exact_phrase=values.get("exact_phrase",""),product_brief=values.get("product_brief",""),listing_title=values.get("listing_title",""),special_instructions=values.get("special_instructions",""),destination_confirmed=values.get("destination_confirmed")=="true",request_id=request.headers.get("x-request-id"))
    background_tasks.add_task(service.run_generation,result["job_id"])
    return RedirectResponse(f"/commerce/jobs/{result['job_id']}/loading",status_code=303,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})


@app.get("/commerce/jobs/{job_id}/loading",response_class=HTMLResponse)
def commerce_loading_route(job_id:str,request:Request):
    _require_local(request);status=CommerceCreationService().safe_status(job_id)
    page=(f"<!doctype html><meta charset='utf-8'><h1>Creating product</h1><p><strong>Brand:</strong> {html_escape(str(status['brand_display_name']))}</p><p><strong>Printify destination:</strong> {html_escape(str(status['printify_shop_title']))} — {int(status['printify_shop_id'])}</p><p><strong>Etsy destination:</strong> {html_escape(str(status['etsy_shop_slug']))}</p><p id='step'><strong>Current step:</strong> {html_escape(str(status['progress_label']))}</p><section id='failure' hidden><h2>Product generation failed</h2><p id='failure-message'></p><p id='draft-state'></p><p><strong>UNPUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p><p><a href='/commerce/new'>Return to new product</a> <a id='retry' href='/commerce/new'>Retry</a></p></section><p id='safety'><strong>UNPUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p><script>async function p(){{let r=await fetch('/commerce/jobs/{html_escape(job_id,quote=True)}/status.json',{{cache:'no-store'}}),s=await r.json();document.getElementById('step').textContent='Current step: '+s.progress_label;if(s.ready_for_review&&s.review_url)location.href=s.review_url;else if(s.failed){{document.getElementById('failure').hidden=false;document.getElementById('safety').hidden=true;document.getElementById('failure-message').textContent=s.failure_message_safe||'Product generation did not complete.';document.getElementById('draft-state').textContent=s.printify_draft_exists?'Printify draft exists':'No Printify draft exists';document.getElementById('retry').hidden=!s.retry_allowed}}else setTimeout(p,1500)}}setTimeout(p,500)</script>")
    return _commerce_ui_response(page)


@app.get("/commerce/jobs/{job_id}/status.json")
def commerce_loading_status_route(job_id:str,request:Request):
    _require_local(request);return JSONResponse(CommerceCreationService().safe_status(job_id),headers={"Cache-Control":"no-store"})


def _commerce_publication_executor(workflow:CommerceWorkflow,job_id:str,*,printify_client:Any=None,etsy_client:Any=None,profile_loader=load_commerce_profile)->CommercePublicationExecutor:
    state=workflow._state(job_id);destination=state.get("destination") or {}
    if destination.get("marketplace_write_route")=="printify_connected_sales_channel":
        bound_loader=lambda required=True:load_commerce_profile_by_id(str(state.get("commerce_profile_id") or ""),required=required)
        client=printify_client or workflow.orchestrator.adapters.client_factory()
        return CommercePublicationExecutor(workflow,provider=PrintifyProviderDraftAdapter(client),marketplace=ConnectedSalesChannelMarketplaceAdapter(),profile_loader=bound_loader)
    profile=profile_loader(required=True);config=profile.get("configuration") or {}
    printify_client=printify_client or workflow.orchestrator.adapters.client_factory()
    if etsy_client is None:
        secrets=SecretProvider({"etsy.app":VAULT/"JamesOS"/"Secrets"/"etsy-app.json","etsy.oauth":VAULT/"JamesOS"/"Secrets"/"etsy-oauth.json"})
        etsy_client=EtsyClient({**secrets.resolve("etsy.app"),**secrets.resolve("etsy.oauth")})
    return CommercePublicationExecutor(workflow,provider=PrintifyProviderDraftAdapter(printify_client),
        marketplace=EtsyMarketplaceAdapter(etsy_client,config.get("etsy_shop_id")),profile_loader=profile_loader)


@app.get("/commerce/proposals/{job_id}/review",response_class=HTMLResponse)
def commerce_proposal_review_route(job_id: str,request: Request,session: str | None=None):
    _require_local(request);workflow=CommerceWorkflow()
    if session is not None:
        try:cookie,max_age=workflow.establish_browser_session(job_id,session)
        except JamesOSError as exc:raise HTTPException(status_code=401,detail="Invalid or expired browser review token") from exc
        response=RedirectResponse(f"/commerce/proposals/{job_id}/review",status_code=303)
        response.set_cookie("jamesos_commerce_review",cookie,max_age=max_age,httponly=True,samesite="strict",path=f"/commerce/proposals/{job_id}")
        response.headers.update({"Cache-Control":"no-store","Referrer-Policy":"no-referrer"});return response
    _browser_authenticate(workflow,job_id,request.cookies.get("jamesos_commerce_review",""))
    return _review_response(_commerce_review_page(workflow,job_id,active_forms=True))


@app.post("/commerce/proposals/{job_id}/approve",response_class=HTMLResponse)
async def commerce_proposal_approve_route(job_id: str,request: Request):
    workflow=CommerceWorkflow();values=await _commerce_form(request,workflow,job_id)
    proposal_sha=values.get("proposal_sha256","");state=workflow._state(job_id);destination=state.get("destination") or {}
    if destination and not hmac.compare_digest(values.get("destination_confirmed",""),str(destination.get("etsy_shop_slug") or "")):raise HTTPException(status_code=403,detail="Destination confirmation required")
    if state.get("stage")=="awaiting_final_approval":workflow.approve(job_id,proposal_sha,confirmed=True)
    try:
        executor=_commerce_publication_executor(workflow,job_id)
        try:executor.execute(job_id=job_id,proposal_sha256=proposal_sha,confirmed=True)
        except JamesOSError:pass
        page=_commerce_review_page(workflow,job_id,active_forms=False)
    finally:workflow.revoke_browser_session(job_id)
    response=_review_response(page);response.delete_cookie("jamesos_commerce_review",path=f"/commerce/proposals/{job_id}");return response


@app.post("/commerce/proposals/{job_id}/request-changes",response_class=HTMLResponse)
async def commerce_proposal_request_changes_route(job_id: str,request: Request,background_tasks:BackgroundTasks):
    workflow=CommerceWorkflow();values=await _commerce_form(request,workflow,job_id)
    try:
        workflow.request_changes(job_id,values.get("proposal_sha256",""),note=values.get("note",""),confirmed=True)
        if (workflow._state(job_id).get("destination") or {}).get("etsy_shop_slug"):
            workflow.revoke_browser_session(job_id);background_tasks.add_task(CommerceRevisionService(workflow).resume,job_id)
            return RedirectResponse(f"/commerce/jobs/{job_id}/loading",status_code=303,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})
        result=CommerceRevisionService(workflow).resume(job_id)
    except JamesOSError as exc:
        page=_commerce_review_page(workflow,job_id,active_forms=True)
        pending=workflow._state(job_id).get("stage")=="revision_requested"
        failing=html_escape(str(exc.context.get("failing_validation") or exc.stage))
        action=html_escape(str(exc.suggested_action or "Correct the revision request and submit again."))
        receipt=("<section id='revision-result' style='background:#fff1cf;border:3px solid #b97800;padding:1.2rem;border-radius:10px;margin:1rem 0'>"
            f"<h2>{'REVISION REQUESTED' if pending else 'Revision request failed'}</h2>"
            f"{'<p><strong>REGENERATION PENDING</strong><br><strong>OLD PROPOSAL CANNOT BE APPROVED</strong></p>' if pending else ''}"
            f"<p><strong>Safe error code:</strong> {html_escape(exc.code)}<br><strong>Failing validation:</strong> {failing}<br>"
            f"<strong>Anything changed:</strong> {'revision request recorded; provider completion pending' if pending else 'no'}</p><p><strong>Safe next action:</strong> {action}</p>"
            "<p><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p></section>")
        page=page.replace("<header>",receipt+"<header>",1)
        if pending:workflow.revoke_browser_session(job_id)
        return _review_response(page,status_code=202 if pending else 422)
    response=RedirectResponse(result["review_url"],status_code=303);response.delete_cookie("jamesos_commerce_review",path=f"/commerce/proposals/{job_id}")
    response.headers.update({"Cache-Control":"no-store","Referrer-Policy":"no-referrer"});return response


@app.post("/commerce/proposals/{job_id}/cancel",response_class=HTMLResponse)
async def commerce_proposal_cancel_route(job_id:str,request:Request):
    workflow=CommerceWorkflow();values=await _commerce_form(request,workflow,job_id);state,proposal,private,root=workflow._current(job_id,values.get("proposal_sha256",""))
    if state.get("stage")!="awaiting_final_approval" or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":raise HTTPException(status_code=409,detail="Product cannot be cancelled in its current state")
    state["stage"]="cancelled";state["cancelled_at"]=__import__("datetime").datetime.now().astimezone().isoformat();proposal["approval_eligible"]=False;private["approval_eligible"]=False
    product_orchestrator._atomic_json(workflow.orchestrator._path(job_id),state);product_orchestrator._atomic_json(root/"current.json",proposal);product_orchestrator._atomic_json(root/"current-private.json",private);workflow.revoke_browser_session(job_id)
    return _review_response("<h1>Product cancelled</h1><p><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p>")


@app.get("/health")
def health():
    return {"status": "ok", "service": "JamesOS"}


@app.post("/intake")
def intake(req: IntakeRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    result = enqueue_job("intake", req.model_dump())
    return {"result": result}


@app.post("/phone-ingest")
def phone_ingest(req: PhoneEventRequest | PhoneBatchRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    data = req.model_dump()
    if "events" in data:
        return ingest_phone_events(data["events"])
    return ingest_phone_event(data)


@app.post("/phone/daily-summary")
def phone_summary(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "report": phone_daily_summary()}


@app.get("/phone-ingestion/health")
def phone_ingestion_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return phone_ingestion_health()


@app.get("/phone-ingestion/methods")
def phone_ingestion_methods_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return phone_ingestion_methods()


@app.post("/quick-note")
def quick_note(req: QuickNoteRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    result = enqueue_job("intake", {
        "title": req.title,
        "content": req.text,
        "source": "mobile_quick_note",
        "source_detail": "flutter_app",
    })
    return {"result": result}


@app.post("/share-link")
def share_link(req: ShareLinkRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    content = f"URL: {req.url}\n\nNote:\n{req.note}"
    result = enqueue_job("intake", {
        "title": req.title,
        "content": content,
        "source": "mobile_share_link",
        "source_detail": req.url,
    })
    return {"result": result}


@app.get("/search")
def search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": search_notes_index(q)}


@app.post("/ask")
def ask(req: AskRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    from datetime import datetime

    result = answer_with_reasoner(req.question, use_ai=req.use_ai, mode=req.mode)

    if req.mode != "private":
        history = _load_chat_history()
        history.append({
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "question": req.question,
            "mode": req.mode,
            "answer": result.get("answer", ""),
            "action": result.get("action", ""),
        })
        _save_chat_history(history)
    return result


@app.get("/ask")
def ask_get(q: str, use_ai: bool = True, mode: str = "personal", x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return answer_with_reasoner(q, use_ai=use_ai, mode=mode)


@app.get("/dashboard")
def dashboard(mode: str = "personal", x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return dashboard_cards(mode)


@app.get("/server/config")
def server_config_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "server": server_config(), "integrations": integration_health()}


@app.get("/server/health")
def server_health(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return service_health()


@app.get("/server/page")
def server_config_page(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return write_server_config_report()


@app.get("/control-center")
def control_center_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_summary()


@app.get("/control-center/health")
def control_center_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_health()


@app.get("/control-center/services")
def control_center_services_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_services()


@app.get("/control-center/integrations")
def control_center_integrations_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_integrations()


@app.get("/control-center/jobs")
def control_center_jobs_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_jobs()


@app.get("/control-center/storage")
def control_center_storage_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_storage()


@app.get("/control-center/summary")
def control_center_summary_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return control_center_human_summary()


@app.get("/planner/health")
def planner_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return planner_health()


@app.post("/planner/plan")
def planner_plan_route(req: PlannerPlanRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return create_plan(req.intent, req.prompt, req.payload)


@app.get("/workers")
def workers_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_workers()


@app.get("/workers/{worker_name}")
def worker_detail_route(worker_name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_worker(worker_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/brands")
def brands_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_brands()


@app.get("/brands/health")
def brands_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return brand_health()


@app.get("/brands/default")
def brands_default_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "brand": get_default_brand(), "execution_enabled": False}


@app.get("/brands/{brand_id}")
def brand_detail_route(brand_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "brand": get_brand(brand_id), "execution_enabled": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/brands/{brand_id}/validate")
def brand_validate_route(brand_id: str, req: BrandValidateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return validate_brand_product_niche(brand_id, req.product_type, req.niche)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/pod-providers")
def pod_providers_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_providers()


@app.get("/pod-providers/health")
def pod_providers_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return provider_health()


@app.get("/pod-providers/{provider_id}")
def pod_provider_detail_route(provider_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "provider": get_provider(provider_id), "writes_enabled": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/models")
def models_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_models()


@app.get("/models/scan")
def models_scan_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return scan_models_and_report()


@app.get("/models/{model_name}")
def model_detail_route(model_name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_model(model_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/workflows")
def workflows_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_workflows()


@app.get("/workflows/scan")
def workflows_scan_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return scan_workflows_and_report()


@app.get("/workflows/{workflow_name}")
def workflow_detail_route(workflow_name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_workflow(workflow_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/recipes")
def recipes_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_recipes()


@app.get("/recipes/by-product/{product_type}")
def recipes_by_product_route(product_type: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return recipes_by_product(product_type)


@app.get("/recipes/{recipe_id:path}")
def recipe_detail_route(recipe_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_recipe(recipe_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/design-planner/health")
def design_planner_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return design_plan_health()


@app.post("/design-planner/plan")
def design_planner_plan_route(req: DesignPlanRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return create_design_plan(
            brand_id=req.brand_id,
            product_type=req.product_type,
            niche=req.niche,
            recipe_id=req.recipe_id,
            quality_target=req.quality_target,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/design-planner/plans/{plan_id}")
def design_planner_plan_detail_route(plan_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return load_design_plan(plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/design-critic/health")
def design_critic_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return design_critic_health()


@app.post("/design-critic/critique-plan")
def design_critic_critique_plan_route(req: CritiquePlanRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    critique = critique_design_plan(req.design_plan, artifact=req.artifact)
    return save_critique(critique)


@app.post("/design-critic/critique-artifact")
def design_critic_critique_artifact_route(req: CritiqueArtifactRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    critique = critique_generated_artifact(req.artifact)
    return save_critique(critique)


@app.get("/design-critic/critiques/{critic_id}")
def design_critic_detail_route(critic_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return load_critique(critic_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/design-runs/create")
def design_runs_create_route(req: DesignRunCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return create_design_run(
        brand_id=req.brand_id,
        product_type=req.product_type,
        niche=req.niche,
        recipe_id=req.recipe_id,
        variations=req.variations,
        quality=req.quality,
        provider=req.provider,
        create_image_jobs=req.create_image_jobs,
    )


@app.get("/design-runs")
def design_runs_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_design_runs()


@app.get("/design-runs/{run_id}")
def design_run_detail_route(run_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_design_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/design-runs/{run_id}/score")
def design_run_score_route(run_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return score_design_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/design-runs/{run_id}/promote-best")
def design_run_promote_best_route(run_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return promote_best(run_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/image-worker/health")
def image_worker_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return image_worker_health()


@app.post("/image-worker/plan")
def image_worker_plan_route(req: ImageWorkerPlanRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return image_worker_plan(req.package)


@app.post("/image-worker/jobs/{job_id}/execute-approved")
def image_worker_execute_approved_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return execute_approved_image_job(job_id)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc)


@app.get("/image-worker/jobs/{job_id}/prepared-workflow")
def image_worker_prepared_workflow_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return prepared_workflow_for_job(job_id)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/analyze-output")
def image_worker_analyze_output_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return analyze_output_image_for_job(job_id)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/approve-concept")
def image_worker_approve_concept_route(
    job_id: str,
    req: ConceptApprovalRequest | None = None,
    x_jamesos_key: str | None = Header(default=None),
):
    require_key(x_jamesos_key)
    try:
        approved_by = (req.approved_by if req else "api_user").strip() or "api_user"
        return approve_concept_for_job(job_id, approved_by=approved_by)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/prepare-transparent-artifact")
def image_worker_prepare_transparent_artifact_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return prepare_transparent_artifact_for_job(job_id)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/approve-transparent-artifact")
def image_worker_approve_transparent_artifact_route(
    job_id: str,
    req: TransparentArtifactApprovalRequest | None = None,
    x_jamesos_key: str | None = Header(default=None),
):
    require_key(x_jamesos_key)
    try:
        approved_by = (req.approved_by if req else "api_user").strip() or "api_user"
        return approve_transparent_artifact_for_job(job_id, approved_by=approved_by)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/prepare-production-artifact")
def image_worker_prepare_production_artifact_route(
    job_id: str,
    req: ProductionArtifactRequest,
    x_jamesos_key: str | None = Header(default=None),
):
    require_key(x_jamesos_key)
    try:
        return prepare_production_artifact_for_job(
            job_id,
            upscale_model_name=req.upscale_model_name,
            confirmed=req.confirmed,
            target_overrides=req.target_overrides,
            production_strategy=req.production_strategy,
            artwork_category=req.artwork_category,
            strategy_selected_by=req.strategy_selected_by,
        )
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.get("/commerce/printify/status")
def printify_status_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return printify_product.status()


@app.get("/commerce/printify/shops")
def printify_shops_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return {"shops": printify_product.normalize_shops(_printify_client().list_shops())}


@app.get("/commerce/printify/catalog/blueprints")
def printify_blueprints_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return _printify_client().list_blueprints()


@app.get("/commerce/printify/catalog/blueprints/{blueprint_id}")
def printify_blueprint_route(blueprint_id: int, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return _printify_client().get_blueprint(blueprint_id)


@app.get("/commerce/printify/catalog/blueprints/{blueprint_id}/providers")
def printify_providers_route(blueprint_id: int, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return _printify_client().list_print_providers_for_blueprint(blueprint_id)


@app.get("/commerce/printify/catalog/blueprints/{blueprint_id}/providers/{provider_id}/variants")
def printify_variants_route(blueprint_id: int, provider_id: int, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return _printify_client().get_variants(blueprint_id, provider_id)


@app.get("/commerce/printify/catalog/blueprints/{blueprint_id}/providers/{provider_id}/shipping")
def printify_shipping_route(blueprint_id: int, provider_id: int, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); return _printify_client().get_shipping(blueprint_id, provider_id)


@app.get("/commerce/printify/jobs/{job_id}/draft-plan")
def printify_draft_plan_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); evidence = printify_product._approved_evidence(job_id)
    path = evidence["job_root"] / "commerce" / "printify" / "product-draft-plan.json"
    if not path.is_file(): raise HTTPException(status_code=404, detail="Printify draft plan not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/commerce/printify/jobs/{job_id}/product")
def printify_product_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key); evidence = printify_product._approved_evidence(job_id)
    path = evidence["job_root"] / "commerce" / "printify" / "product-draft.json"
    if not path.is_file(): raise HTTPException(status_code=404, detail="Printify product draft not found.")
    record = json.loads(path.read_text(encoding="utf-8"))
    return _printify_client().get_product(record["shop_id"], record["printify_product_id"])


@app.post("/commerce/printify/jobs/{job_id}/upload-approved-artwork")
def printify_upload_route(job_id: str, req: PrintifyUploadRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try: return printify_product.upload_approved_artwork(job_id, confirmed=req.confirmed, client=_printify_client(), image_url=req.image_url)
    except JobQueueError as exc: raise StateConflictError("STATE_CONFLICT", diagnostic_message=str(exc), operation="printify.upload",
        stage="validation", context={"job_id": job_id}, state={"external_write_attempted": False}) from exc


@app.post("/commerce/printify/jobs/{job_id}/create-product-draft")
def printify_create_draft_route(job_id: str, req: PrintifyCreateDraftRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try: return printify_product.create_product_draft(job_id, confirmed=req.confirmed, client=_printify_client())
    except JobQueueError as exc: raise StateConflictError("STATE_CONFLICT", diagnostic_message=str(exc), operation="printify.create_product",
        stage="validation", context={"job_id": job_id}, state={"external_write_attempted": False}) from exc


@app.post("/image-worker/jobs/{job_id}/approve-production-artifact")
def image_worker_approve_production_artifact_route(
    job_id: str,
    req: ProductionArtifactApprovalRequest,
    x_jamesos_key: str | None = Header(default=None),
):
    require_key(x_jamesos_key)
    try:
        return approve_production_artifact_for_job(
            job_id,
            approved_by=req.approved_by,
            confirmed=req.confirmed,
        )
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/jobs/{job_id}/validate-upscale-model")
def image_worker_validate_upscale_model_route(
    job_id: str,
    req: UpscaleValidationRequest,
    x_jamesos_key: str | None = Header(default=None),
):
    require_key(x_jamesos_key)
    try:
        return validate_upscale_model_for_job(
            job_id,
            upscale_model_name=req.upscale_model_name,
            confirmed=req.confirmed,
            bleed_iterations=req.bleed_iterations,
            alpha_threshold=req.alpha_threshold,
            alpha_resize_method=req.alpha_resize_method,
        )
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.get("/image-worker/upscale-models")
def image_worker_upscale_models_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return list_upscale_models()
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc)


@app.get("/image-worker/jobs/{job_id}/comfy-response")
def image_worker_comfy_response_route(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return comfy_response_for_job(job_id)
    except JobQueueError as exc:
        from jamesos.services.image_worker import structured_error

        return structured_error(exc, job_id=job_id)


@app.post("/image-worker/create-test-job")
def image_worker_create_test_job_route(req: TestImageJobRequest | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    data = req or TestImageJobRequest()
    try:
        return create_test_image_job(
            positive_prompt=data.positive_prompt,
            negative_prompt=data.negative_prompt,
            seed=data.seed,
            width=data.width,
            height=data.height,
            brand_id=data.brand_id,
            draft_path=data.draft_path,
        )
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/prompts")
def prompts_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return load_prompt_templates()


@app.get("/prompts/{template_name}")
def prompt_detail_route(template_name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_prompt_template(template_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/assets")
def assets_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return scan_assets()


@app.get("/styles")
def styles_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_styles()


@app.get("/styles/{style_name}")
def style_detail_route(style_name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_style(style_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/comfyui/health")
def comfyui_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return comfyui_health()


@app.get("/jobs")
def jobs(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "jobs": list_jobs(status)}
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs/{job_id}")
def job_detail(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs")
def job_create(req: JobCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return create_job(
        req.type,
        req.payload,
        priority=req.priority,
        requires_approval=req.requires_approval,
        steps=req.steps,
    )


@app.post("/jobs/{job_id}/approve")
def job_approve(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return approve_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/fail")
def job_fail(job_id: str, req: JobFailRequest | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return fail_job(job_id, reason=req.reason if req else "")
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/creative-studio/health")
def creative_studio_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return creative_studio_health()


@app.get("/creative-studio/pipelines")
def creative_studio_pipelines(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "pipelines": list_pipelines(status)}
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creative-studio/pipelines")
def creative_studio_pipeline_create(req: CreativePipelineCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return create_pipeline(req.payload, priority=req.priority)
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/creative-studio/pipelines/{job_id}")
def creative_studio_pipeline_detail(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_pipeline(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/commerce_shop/health")
def commerce_shop_health_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return commerce_shop_health()


@app.post("/commerce_shop/generate-daily-drafts")
def commerce_shop_generate_daily_drafts_route(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return generate_commerce_shop_daily_drafts()


@app.get("/commerce_shop/drafts")
def commerce_shop_drafts_route(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return list_commerce_shop_drafts(status=status)


@app.get("/commerce_shop/drafts/{date}")
def commerce_shop_drafts_for_date_route(date: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return commerce_shop_drafts_for_date(date)


@app.get("/creative-studio/jobs")
def creative_studio_jobs(status: str | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return {"status": "ok", "jobs": list_creative_jobs(status)}
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/creative-studio/jobs")
def creative_studio_job_create(req: CreativeJobCreateRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return create_creative_job(req.type, req.payload, priority=req.priority)
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/creative-studio/jobs/{job_id}")
def creative_studio_job_detail(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return get_creative_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/creative-studio/jobs/{job_id}/approve")
def creative_studio_job_approve(job_id: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return approve_creative_job(job_id)
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/creative-studio/jobs/{job_id}/fail")
def creative_studio_job_fail(job_id: str, req: JobFailRequest | None = None, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    try:
        return fail_creative_job(job_id, reason=req.reason if req else "")
    except JobQueueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/daily-briefing")
def daily_briefing(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_daily_briefing()}


@app.get("/status-report")
def status_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": generate_status_report()}


@app.get("/mobile/home")
def mobile_home(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    reports = VAULT / "JamesOS" / "Reports"
    home = VAULT / "Home.md"

    def read_report(name: str) -> str:
        path = reports / f"{name}.md"
        return path.read_text(encoding="utf-8", errors="ignore")[:4000] if path.exists() else ""

    return {
        "status": "ok",
        "home": home.read_text(encoding="utf-8", errors="ignore")[:4000] if home.exists() else "",
        "daily_briefing": read_report("Daily Briefing"),
        "proactive_assistant": read_report("Proactive Assistant"),
        "work_intelligence": read_report("Work Intelligence"),
        "people": read_report("People"),
    }


@app.post("/memory")
def memory_add(req: MemoryRequest, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return remember(req.text, req.source, req.importance)


@app.get("/memory/search")
def memory_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return search_memory(q)


@app.get("/graph/search")
def graph_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return graph_lookup(q)


@app.post("/graph/build")
def graph_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_knowledge_graph()}


@app.get("/knowledge-graph/edit-capabilities")
def knowledge_graph_edit_capabilities(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return edit_capabilities()


@app.get("/typed/search")
def typed_search(q: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return search_typed_indexes(q)


@app.post("/typed/build")
def typed_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_typed_indexes()}


@app.post("/brain/summarize-chat")
def brain_summarize_chat(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": summarize_chat_history()}


@app.post("/attachments/ingest")
def attachments_ingest(files: list[UploadFile] = File(...), x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return ingest_attachments(files)


@app.post("/attachments/process-pending")
def attachments_process_pending(limit: int = 10, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return process_pending_attachment_jobs(limit=limit)


@app.post("/files/build")
def files_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"result": build_file_knowledge()}


@app.get("/")
def index():
    return HTMLResponse("<h1>JamesOS API</h1><p>Service is running.</p>")


def _load_chat_history() -> list[dict]:
    import json
    if not CHAT_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(CHAT_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_chat_history(history: list[dict]) -> None:
    import json
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHAT_HISTORY_FILE.write_text(json.dumps(history[-500:], indent=2), encoding="utf-8")
