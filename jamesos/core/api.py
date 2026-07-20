import json
import hmac
import re
from hashlib import sha256
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File,Form,BackgroundTasks
from fastapi.responses import FileResponse,HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from PIL import Image

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
from jamesos.services.ollama_service import ask_ollama, ollama_enabled, chat_diagnostics, ollama_readiness
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
from jamesos.services.commerce_mockup_review import MockupReviewService
from jamesos.services.commerce_mockup_composer import DeterministicMockupComposer,MockupTemplateRegistry
from jamesos.services.commerce_mockup_template_ingest import MockupTemplateIngestService
from jamesos.services.application_shell import WorkspaceChatService,VIEWS,application_shell_diagnostics
from jamesos.services.layout_manager import LayoutManager,THEMES
from jamesos.services.context_dock import NavigationContext,build_navigation
from jamesos.services.shell_health import ShellHealthService
from jamesos.services.shell_dashboard import ShellDashboardService
from jamesos.services.shell_secrets import ShellSecretStore
from jamesos.services.ehf_admin import EHFAdminService
from jamesos.services.shell_profile_settings import ShellProfileSettings
from jamesos.services.shell_attachments import MAX_BYTES,delete_pending_attachment,process_chat_attachments,store_attachment,verify_attachments
from jamesos.services.private_chat import PrivateChatPolicy,affirm_adult_session,end_adult_session,validate_adult_session
from jamesos.services.access_policy import AccessPolicy
from jamesos.services.commerce_copilot import CommerceCopilotService
from jamesos.services.book_opportunity_scout import BookOpportunityScoutService
from jamesos.services.coloring_book_producer import ColoringBookProducer
from jamesos.core.agents.secrets import SecretProvider
from jamesos.core.profiles.selection import load_commerce_profile,list_commerce_profiles,load_commerce_profile_by_id,selected_profile_id
from jamesos.integrations.etsy_client import EtsyClient
from jamesos.services.worker_registry import get_worker, list_workers
from jamesos.services.workflow_manager import get_workflow, list_workflows, scan_and_report as scan_workflows_and_report
from jamesos.core.agency.routes import router as agency_router
from jamesos.core.agency.shell_registry import ShellAgencyRegistry

API_KEY_FILE = VAULT / "JamesOS" / "Secrets" / "api_key.txt"
CHAT_HISTORY_FILE = VAULT / "JamesOS" / "Memory" / "chat_history.json"

app = FastAPI(title="JamesOS API")
_COMMERCE_CREATE_CSRF=__import__("secrets").token_urlsafe(32)


@app.middleware("http")
async def private_network_access_boundary(request:Request,call_next):
    try:AccessPolicy.from_runtime_env().authorize(request)
    except HTTPException as exc:return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail})
    return await call_next(request)
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
    AccessPolicy.from_runtime_env().authorize(request)


def _require_read_only_asset(request:Request)->None:
    AccessPolicy.from_runtime_env().authorize_read_only_asset(request)


def _browser_authenticate(workflow: CommerceWorkflow,job_id: str,cookie: str) -> None:
    try:workflow.authenticate_browser_session(job_id,cookie)
    except JamesOSError as exc:raise HTTPException(status_code=401,detail="Invalid or expired browser review session") from exc


def _validate_commerce_origin(request: Request) -> None:
    AccessPolicy.from_runtime_env().authorize(request,require_origin=True,validate_client=False)


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
        panel=(f"<section id='destination-panel'><strong>Brand:</strong> {html_escape(str(job_state.get('brand_display_name') or ''))}<br><strong>Profile:</strong> {html_escape(str(job_state.get('commerce_profile_id') or job_state.get('profile_id') or ''))}<br>"
            f"<strong>Printify:</strong> {html_escape(str(destination.get('printify_shop_title') or ''))} — {html_escape(str(destination.get('printify_shop_id') or ''))}<br><strong>Etsy:</strong> {html_escape(str(destination.get('etsy_shop_slug') or ''))}<br>"
            f"<strong>Revision:</strong> {int(job_state.get('revision_number') or 0)}<br><strong>Status:</strong> UNPUBLISHED<br><strong>Order:</strong> NOT CREATED<br>NO ORDER CREATED</section>")
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
        "Content-Security-Policy":"default-src 'none'; img-src 'self'; script-src 'unsafe-inline'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})


@app.get("/app/health")
def application_shell_health_route(request:Request):
    _require_local(request)
    return ShellHealthService().status(list_commerce_profiles(enabled_only=True))


@app.get("/app/access-status")
def application_access_status_route(request:Request):
    policy=AccessPolicy.from_runtime_env();policy.authorize(request)
    return policy.status(request)


@app.get("/app/dashboard-status")
def application_dashboard_status_route(request:Request):
    _require_local(request)
    return ShellDashboardService(jobs=list_jobs).status(list_commerce_profiles(enabled_only=True))


@app.get("/app/admin/credentials")
def application_credentials_status_route(request:Request):
    _require_local(request)
    return {"providers": ShellSecretStore().status()}


@app.post("/app/admin/credentials/{provider}")
async def application_credentials_save_route(provider:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ShellSecretStore().save(provider,str(values.get("secret") or ""))
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.delete("/app/admin/credentials/{provider}")
async def application_credentials_delete_route(provider:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ShellSecretStore().delete(provider,confirmed=values.get("confirmed") is True)
    except PermissionError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


def _ehf_filters(request: Request) -> dict[str, str]:
    allowed={"severity","operation","stage","job","date_from","date_to","resolved"}
    return {key:str(value)[:120] for key,value in request.query_params.items() if key in allowed}


@app.get("/app/admin/errors")
def application_ehf_list_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    return EHFAdminService().records(_ehf_filters(request))


@app.get("/app/admin/errors/export")
def application_ehf_export_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    return EHFAdminService().export(_ehf_filters(request))


@app.get("/app/admin/errors/{error_id}")
def application_ehf_detail_route(error_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    try:return EHFAdminService().detail(error_id)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    except LookupError as exc:raise HTTPException(status_code=404,detail="Error record not found") from exc


@app.post("/app/admin/errors/{error_id}/{action}")
async def application_ehf_update_route(error_id:str,action:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return EHFAdminService().update(error_id,action=action)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    except LookupError as exc:raise HTTPException(status_code=404,detail="Error record not found") from exc


@app.post("/app/admin/commerce-profiles/{profile_id}")
async def application_profile_settings_route(profile_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.pop("csrf_token","") if isinstance(values,dict) else ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ShellProfileSettings().save(profile_id,values)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.get("/app",response_class=HTMLResponse)
def application_shell_route(request:Request):
    _require_local(request);profiles=list_commerce_profiles(enabled_only=True);profile_ids={str(item.get("profile_id") or "") for item in profiles};active=str(request.query_params.get("view") or "dashboard");requested_job=str(request.query_params.get("job_id") or "");requested_project=str(request.query_params.get("project_id") or "");agency_snapshot=ShellAgencyRegistry().snapshot();private_policy=PrivateChatPolicy().status()
    if active not in VIEWS:active="dashboard"
    selected=selected_profile_id()
    if selected not in profile_ids:selected=str((profiles[0] if profiles else {}).get("profile_id") or "")
    cards=[];profile_ui={}
    for profile in profiles:
        config=profile.get("configuration") or {};pid=html_escape(str(profile.get("profile_id") or ""),quote=True);display=html_escape(str(profile.get("display_name") or pid));shop=html_escape(str(config.get("printify_shop_title") or display));slug=html_escape(str(config.get("etsy_shop_slug") or ""));shop_id=int(config["printify_shop_id"])
        cards.append(f"<option value='{pid}' data-brand='{display}' data-printify-title='{shop}' data-shop-id='{shop_id}' data-etsy='{slug}' {'selected' if str(profile.get('profile_id') or '')==selected else ''}>{display}</option>")
        profile_ui[str(profile.get("profile_id") or "")]= {
            "garment_colors":config.get("default_garment_colors") or config.get("garment_colors") or [],
            "artwork_palette":config.get("artwork_palette") or config.get("palette") or [],
            "blueprint":config.get("printify_blueprint_id") or config.get("blueprint_id"),
            "provider":config.get("print_provider_id"),"placement":config.get("placement") or config.get("print_placement"),
            "brand_voice":config.get("brand_voice") or [],"listing_guidance":config.get("listing_policy_reference") or "",
            "form_defaults":{},
        }
    initial_navigation=build_navigation(NavigationContext(active_view=active));dock=[]
    for item in initial_navigation:
        badge=f"<span class='dock-badge {html_escape(str(item.get('badge') or ''))}'>{html_escape(str(item.get('badge') or '').replace('_',' '))}</span>" if item.get("badge") else ""
        dock.append(f"<button type='button' data-view='{html_escape(item['view_id'],quote=True)}' data-nav-id='{html_escape(item['item_id'],quote=True)}' data-locked='{'true' if item['locked'] else 'false'}'>{html_escape(item['label'])}{badge}</button>")
    profile_ui_json=json.dumps(profile_ui,ensure_ascii=False).replace("<","\\u003c").replace(">","\\u003e").replace("&","\\u0026")
    page=("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>JamesOS</title><style>"
        ":root{color-scheme:dark;--line:#30364a;--panel:#11131b;--surface:#191c28;--ink:#f1f3ff;--muted:#a6adc8;--accent:#8b5cf6;--ready:#39d98a;--chat-width:420px}*{box-sizing:border-box}body{margin:0;font:15px system-ui;color:var(--ink);background:#0b0d13}.shell{display:grid;grid-template-columns:var(--chat-width) 7px minmax(0,1fr);min-height:100vh}.divider{background:#23283a;cursor:col-resize;touch-action:none}.divider:hover,.divider.dragging{background:var(--accent)}.chat{position:sticky;top:0;height:100vh;padding:1rem;display:flex;flex-direction:column;background:var(--panel);z-index:4}.brand{display:flex;justify-content:space-between;align-items:start}.brand h1{margin:0}.muted,small{color:var(--muted)}.ready{color:var(--ready)}.transcript{flex:1;overflow:auto;margin:.8rem 0;border-block:1px solid var(--line);padding:.5rem 0}.turn{white-space:pre-wrap;padding:.55rem;border-radius:.55rem;margin:.35rem 0}.assistant{background:#211b38;border-left:3px solid var(--accent)}textarea,input[type=text]{width:100%;padding:.65rem;margin:.3rem 0 .8rem;background:#10131c;border:1px solid var(--line);color:var(--ink)}.chat-actions,.activity-actions,.topbar,.layout-toolbar,.context-dock{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}button,.button,select{padding:.55rem .75rem;cursor:pointer;background:#24283a;color:var(--ink);border:1px solid #454c68;border-radius:.45rem}button:hover,[data-view]:focus{border-color:var(--accent)}.context-dock{position:sticky;top:58px;z-index:2;padding:.65rem 0;background:#0b0d13;border-bottom:1px solid var(--line);margin-bottom:1rem}.context-dock button[data-locked=true]{border-color:#66558f}.dock-badge{margin-left:.4rem;padding:.1rem .35rem;border-radius:1rem;font-size:.72rem;background:#34394e}.dock-badge.ready{background:#174c35;color:#8ff0bd}.dock-badge.warning{background:#5a3614;color:#ffd39b}.dock-badge.progress{background:#29205a;color:#c8b8ff}.dock-badge.pending_approval{background:#594913;color:#ffe69b}.workspace{min-width:0}.topbar{position:sticky;top:0;padding:.8rem 1rem;border-bottom:1px solid var(--line);background:#10121a;z-index:3}.topbar h2{margin:0 auto 0 0}.content{padding:1.25rem;max-width:1200px}.layout-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));grid-auto-rows:minmax(48px,auto);gap:.75rem}.layout-panel{grid-column:var(--panel-column,1)/span var(--panel-width,12);grid-row:var(--panel-row,1)/span var(--panel-height,1);border:1px solid var(--line);border-radius:.7rem;background:var(--surface);overflow:auto}.panel-title{display:flex;justify-content:space-between;padding:.65rem .8rem;border-bottom:1px solid var(--line);font-weight:700}.panel-content{padding:.8rem}.customizing .layout-panel:not([data-layout-locked=true]){resize:both;outline:1px dashed var(--accent)}.customizing .layout-panel:not([data-layout-locked=true]) .panel-title{cursor:grab}.customizing .layout-panel[data-layout-locked=true]{outline:1px solid #d49b20}.layout-toolbar[hidden]{display:none}.shops{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.75rem}.shop-card{border:1px solid var(--line);background:var(--surface);border-radius:.7rem;padding:.8rem}.shop-card:has(input:checked){border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}.shop-card small{display:block;margin:.35rem 0 0 1.5rem}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.wide{grid-column:1/-1}.confirmation{border:2px solid #d49b20;background:#2a2214;padding:.8rem;border-radius:.7rem;margin:.6rem 0}.safeguard{color:var(--ready);border:1px solid #246b4a;background:#10271d;padding:.65rem;border-radius:.55rem}.activity{max-height:8rem;overflow:auto;font-size:.85rem}.drawer-toggle{display:none}@media(max-width:800px){.shell{display:block}.divider{display:none}.chat{position:fixed;inset:0 auto 0 0;width:min(420px,92vw);transform:translateX(-105%);transition:.2s}.chat.open{transform:none}.drawer-toggle{display:inline-block}.field-grid{display:block}.layout-grid{display:block}.layout-panel{margin-bottom:.75rem;resize:none!important}.context-dock{top:54px;overflow-x:auto;flex-wrap:nowrap}}"
        "[hidden]{display:none!important}.agency-registry>.layout-panel{grid-column:auto;grid-row:auto}.brand h1{display:flex;align-items:center;gap:.5rem}.health-dot{width:.85rem;height:.85rem;padding:0;border:0;border-radius:50%;background:#d49b20}.health-dot.green{background:#39d98a}.health-dot.yellow{background:#e4b13c}.health-dot.red{background:#f05b68}.health-detail{margin:.55rem 0;padding:.6rem;border:1px solid var(--line);border-radius:.55rem;background:#10131c}.health-detail[hidden]{display:none}.health-detail ul{margin:.4rem 0;padding-left:1.2rem}.context-dock{top:0;padding:.65rem 1.25rem;background:#10121a;justify-content:space-between}.dock-items,.dock-tools{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}.profile-select{width:100%;margin:.35rem 0 .65rem}.profile-guidance{color:var(--muted);font-size:.9rem}.destination-summary p{margin:.25rem 0}"
        f"</style></head><body><div class='shell' id='app-shell'><aside class='chat' id='chat'><div class='brand'><div><h1>JamesOS <button type='button' id='health-dot' class='health-dot yellow' aria-label='System health: checking' aria-expanded='false'></button></h1><p class='muted'>Your local workspace assistant</p></div><button type='button' id='close-chat' class='drawer-toggle'>Close</button></div><section id='health-detail' class='health-detail' aria-label='System health details' hidden><strong id='health-label'>Checking local systems…</strong><ul id='health-systems'></ul></section><div class='transcript' id='transcript' aria-live='polite'></div><div id='confirmations' data-component='confirmation'></div><textarea id='chat-message' maxlength='2000' rows='4' placeholder='Ask JamesOS to help with this workspace'></textarea><div class='chat-actions' data-component='action_bar'><button type='button' id='send'>Send</button><button type='button' id='stop' disabled>Stop</button><button type='button' id='retry' disabled>Retry</button><button type='button' id='reset'>Reset</button></div><p id='chat-state' aria-live='polite'>Ready.</p><p id='shell-init-error' class='dock-badge warning' role='alert' hidden></p><div class='activity-actions'><strong>Activity</strong><button type='button' id='undo' disabled>Undo</button></div><div class='activity' id='activity'></div></aside><div class='divider' id='shell-divider' role='separator' aria-label='Resize chat pane' aria-orientation='vertical' tabindex='0'></div><main class='workspace'><nav class='context-dock' id='context-dock' aria-label='Context navigation'><button type='button' class='drawer-toggle' id='open-chat'>JamesOS</button><span class='dock-items' id='context-items'>{''.join(dock)}</span><span class='dock-tools'><button type='button' id='customize-layout'>Customize layout</button><span class='layout-toolbar' id='layout-toolbar' hidden><label>Theme <select id='theme-chooser'><option value='jamesos-dark'>JamesOS Dark</option></select></label><button type='button' id='save-layout'>Save</button><button type='button' id='cancel-layout'>Cancel</button><button type='button' id='reset-layout'>Reset</button></span><span id='identity'>Profile: "
        f"{html_escape(selected)}</span><span id='job-status'></span></span></nav><section class='content'><section id='commerce-new' class='layout-grid'><section class='layout-panel' data-panel-id='commerce_form' data-component='form' data-layout-locked='false' draggable='false'><header class='panel-title'>Commerce Creator <span></span></header><div class='panel-content'><form id='commerce-form' method='post' action='/commerce/new'><input type='hidden' name='csrf_token' value='"
        f"{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}'><label for='commerce-profile'><strong>Commerce profile</strong></label><select class='profile-select' id='commerce-profile' name='commerce_profile_id' required>{''.join(cards)}</select><div class='profile-guidance' id='profile-guidance'></div><div class='field-grid'><label>Exact phrase<textarea id='exact_phrase' name='exact_phrase' maxlength='500'></textarea></label><label>Listing title<input id='listing_title' type='text' name='listing_title' maxlength='140'></label><label class='wide'>Product brief<textarea id='product_brief' name='product_brief' maxlength='5000' required></textarea></label><label class='wide'>Special instructions<textarea id='special_instructions' name='special_instructions' maxlength='3000'></textarea></label></div><input type='hidden' name='destination_confirmed' value='true'><button type='button' id='prepare-generation'>Generate unpublished draft</button></form></div></section><aside class='layout-panel' data-panel-id='destination' data-component='card' data-layout-locked='true'><header class='panel-title'>Destination <span>🔒</span></header><div class='panel-content destination-summary' id='destination'><p><strong id='destination-profile'></strong></p><p id='destination-printify'></p><p id='destination-etsy'></p><p class='safeguard' id='destination-status'>UNPUBLISHED</p></div></aside><aside class='layout-panel' data-panel-id='publication_status' data-component='status_banner' data-layout-locked='true'><header class='panel-title'>Publication safeguards <span>🔒</span></header><div class='panel-content safeguard'><strong>UNPUBLISHED DRAFT ONLY</strong><br>No order will be created.</div></aside><aside class='layout-panel' data-panel-id='external_confirmation' data-component='confirmation' data-layout-locked='true'><header class='panel-title'>External action confirmation <span>🔒</span></header><div class='panel-content'>Provider actions require explicit confirmation.</div></aside></section><section id='agency-view' hidden><h3>The Agency</h3><div class='layout-grid'><article class='layout-panel'><header class='panel-title'>Active agents <span></span></header><div class='panel-content'>No active agents.</div></article><article class='layout-panel'><header class='panel-title'>Current runs <span></span></header><div class='panel-content'>No current runs.</div></article><article class='layout-panel'><header class='panel-title'>Pending approvals <span></span></header><div class='panel-content'>No pending approvals.</div></article><article class='layout-panel'><header class='panel-title'>Recent results <span></span></header><div class='panel-content'>No recent results.</div></article><article class='layout-panel'><header class='panel-title'>Agent tools <span></span></header><div class='panel-content'>Registered tools appear here.</div></article></div></section><section id='admin-view' hidden><h3>Admin</h3><div class='panel-content'>Profiles · Service status · Themes · Layouts · Permissions · Diagnostics</div><section class='layout-panel' data-layout-locked='true' aria-labelledby='access-status-title'><header class='panel-title' id='access-status-title'>Private-network access <span>🔒</span></header><div class='panel-content' id='access-status' aria-live='polite'><p>Access mode: <strong id='access-mode'>checking</strong></p><p>Trusted hostname: <strong id='access-host'>checking</strong></p><p>HTTPS state: <strong id='access-https'>checking</strong></p><p>Direct client/proxy type: <strong id='access-connection'>checking</strong></p><p>Access scope: <strong id='access-scope'>checking</strong></p><p id='access-warning' class='dock-badge warning' hidden></p></div></section></section><section id='generic-view' hidden><h3 id='generic-title'></h3><p id='generic-copy'></p></section></section></main></div><script>document.addEventListener('DOMContentLoaded',()=>{{"
        f"const csrf='{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}',allowedViews={json.dumps(sorted(VIEWS))},initialView={json.dumps(active)},initialNavigation={json.dumps(initial_navigation)},profileUi={profile_ui_json},fields=['exact_phrase','product_brief','listing_title','special_instructions'];"
        "let conversation=localStorage.getItem('jamesos-conversation-id')||crypto.randomUUID(),activeView=initialView,selectedJob='',turns=[],activity=[],undoStack=[],lastMessage='',controller=null,applyingProfile=false,lastProfile='';localStorage.setItem('jamesos-conversation-id',conversation);const q=x=>document.getElementById(x),reportInitError=()=>{const node=q('shell-init-error');if(node){node.hidden=false;node.textContent='JamesOS could not initialize one optional shell control.'}},bind=(id,type,handler)=>{const node=q(id);if(!node){reportInitError();return null}node.addEventListener(type,handler);return node},profileSelect=q('commerce-profile'),fieldMeta=Object.fromEntries(fields.map(k=>[k,{dirty:false,autoValue:''}]));function selected(){return profileSelect.selectedOptions[0]}function formState(){return Object.fromEntries(fields.map(k=>[k,q(k).value]))}fields.forEach(k=>q(k).addEventListener('input',()=>{if(!applyingProfile)fieldMeta[k].dirty=true}));function identity(){const x=selected();if(!x)return;const ui=profileUi[x.value]||{};q('identity').textContent='Profile: '+x.dataset.brand;q('destination-profile').textContent=x.dataset.brand;q('destination-printify').textContent='Printify: '+x.dataset.printifyTitle+' — '+x.dataset.shopId;q('destination-etsy').textContent='Etsy: '+x.dataset.etsy;q('profile-guidance').textContent=['Garments: '+(ui.garment_colors||[]).join(', '),'Artwork palette: '+(ui.artwork_palette||[]).join(', '),'Brand voice: '+(ui.brand_voice||[]).join(', '),'Listing: '+(ui.listing_guidance||'configured policy')].join(' · ')}function snapshot(){return {form:formState(),profile:profileSelect.value,fieldMeta:structuredClone(fieldMeta)}}function applyProfile(profileId,record=true){if(selectedJob)return;const before=snapshot();profileSelect.value=profileId;const ui=profileUi[profileId]||{},changed=[];applyingProfile=true;Object.entries(ui.form_defaults||{}).forEach(([k,v])=>{if(fields.includes(k)&&v&&!fieldMeta[k].dirty&&(!q(k).value||q(k).value===fieldMeta[k].autoValue)){if(q(k).value!==v){q(k).value=v;changed.push(k)}fieldMeta[k].autoValue=v}});applyingProfile=false;identity();lastProfile=profileId;if(record){undoStack.push(before);log('Profile '+selected()?.dataset.brand+' updated destination and '+(changed.length?changed.join(', '):'profile guidance'))}}function restore(s){fields.forEach(k=>q(k).value=s.form[k]||'');profileSelect.value=s.profile;Object.assign(fieldMeta,s.fieldMeta||{});lastProfile=s.profile;identity()}lastProfile=profileSelect.value;profileSelect.addEventListener('change',()=>{const next=profileSelect.value;profileSelect.value=lastProfile;applyProfile(next)});identity();function renderTurns(){q('transcript').replaceChildren();turns.slice(-30).forEach(t=>{let p=document.createElement('div');p.className='turn '+t.role;p.textContent=(t.role==='user'?'You: ':'JamesOS: ')+t.text;q('transcript').appendChild(p)});q('transcript').scrollTop=q('transcript').scrollHeight}function log(text){activity.push(text);activity=activity.slice(-50);q('activity').replaceChildren(...activity.map(x=>{let p=document.createElement('div');p.textContent=x;return p}));q('undo').disabled=!undoStack.length}function change(mutator,label){undoStack.push(snapshot());mutator();identity();log(label)}function navigate(view){if(!allowedViews.includes(view))return;activeView=view;const commerce=view==='commerce.new';q('commerce-new').hidden=!commerce;q('generic-view').hidden=commerce;const titles={'dashboard':'Dashboard','commerce.new':'Commerce Creator','commerce.loading':'Generating product','commerce.review':'Product review','commerce.diagnostics':'Commerce diagnostics','commerce.published':'Published product','jobs.list':'Jobs','jobs.detail':'Job detail','profiles':'Profiles','settings':'Settings','diagnostics':'Diagnostics'};if(!commerce){q('generic-title').textContent=titles[view];q('generic-copy').textContent=view==='dashboard'?'Choose a workspace or ask JamesOS for help.':'This workspace is available in the JamesOS shell.'}history.replaceState(null,'','/app?view='+encodeURIComponent(view));log('Opened '+titles[view])}async function watchJob(){if(!selectedJob)return;try{const response=await fetch('/commerce/jobs/'+encodeURIComponent(selectedJob)+'/status.json',{cache:'no-store'}),status=await response.json();q('job-status').textContent=status.progress_label||status.stage;if(status.ready_for_review){navigate('commerce.review');return}if(status.failed){navigate('commerce.diagnostics');q('generic-copy').textContent=status.failure_message_safe||'Product preparation did not complete.';return}setTimeout(watchJob,1500)}catch(e){setTimeout(watchJob,2500)}}document.querySelectorAll('[data-view]').forEach(x=>x.onclick=()=>navigate(x.dataset.view));navigate(activeView);function confirm(command){q('confirmations').replaceChildren();let box=document.createElement('div');box.className='confirmation';let p=document.createElement('p');p.textContent=command.message;let yes=document.createElement('button');yes.type='button';yes.textContent=command.action==='publish'?'Open destination confirmation':'Confirm';yes.onclick=()=>{if(command.action==='start_generation'){q('commerce-form').requestSubmit()}else if(command.action==='request_revision'){log('Revision prepared for explicit submission')}else{log('Publish confirmation requires the destination-specific review control')} };let no=document.createElement('button');no.type='button';no.textContent='Cancel';no.onclick=()=>box.remove();box.append(p,yes,no);q('confirmations').appendChild(box)}function execute(commands){for(const c of commands){if(c.type==='navigate')navigate(c.view);else if(c.type==='select_profile'){if(!selectedJob&&profileUi[c.profile_id])applyProfile(c.profile_id)}else if(c.type==='form_patch')change(()=>Object.entries(c.fields).forEach(([k,v])=>{if(fields.includes(k))q(k).value=v}),'Updated '+Object.keys(c.fields).join(', '));else if(c.type==='form_clear')change(()=>c.fields.forEach(k=>{if(fields.includes(k))q(k).value=''}),'Cleared '+c.fields.join(', '));else if(c.type==='open_job'){selectedJob=c.job_id;profileSelect.disabled=true;navigate('commerce.loading');q('job-status').textContent='Job: '+selectedJob;watchJob()}else if(c.type==='open_review'){selectedJob=c.job_id;profileSelect.disabled=true;navigate('commerce.review');q('job-status').textContent='Review: '+selectedJob}else if(c.type==='show_notification'){turns.push({role:'assistant',text:c.message});renderTurns()}else if(c.type==='show_confirmation')confirm(c)}}async function send(){const message=q('chat-message').value.trim();if(!message)return;lastMessage=message;q('retry').disabled=true;q('send').disabled=true;q('stop').disabled=false;q('chat-state').textContent='Thinking…';turns.push({role:'user',text:message});renderTurns();controller=new AbortController();try{const x=selected(),response=await fetch('/app/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({csrf_token:csrf,conversation_id:conversation,message,active_view:activeView,active_profile_id:x?.value||'',selected_job_id:selectedJob,form:formState()})});let data={};try{data=await response.json()}catch(e){}if(!response.ok)throw new Error(data.message||'JamesOS could not complete the request.');turns.push({role:'assistant',text:data.message});(data.warnings||[]).forEach(x=>turns.push({role:'assistant',text:'Warning: '+x}));renderTurns();execute(data.commands||[]);q('chat-message').value='';q('chat-state').textContent='Ready.'}catch(e){if(e.name!=='AbortError'){turns.push({role:'assistant',text:'Safe error: '+(e.message||'Request failed.')});renderTurns()}q('chat-state').textContent=e.name==='AbortError'?'Stopped.':'Safe error.';q('retry').disabled=false}finally{controller=null;q('send').disabled=false;q('stop').disabled=true}}bind('send','click',send);bind('stop','click',()=>controller?.abort());bind('retry','click',()=>{q('chat-message').value=lastMessage;send()});bind('reset','click',()=>{conversation=crypto.randomUUID();localStorage.setItem('jamesos-conversation-id',conversation);turns=[];activity=[];undoStack=[];renderTurns();q('activity').replaceChildren();q('undo').disabled=true;q('chat-state').textContent='Conversation reset.'});bind('undo','click',()=>{const s=undoStack.pop();if(s){restore(s);log('Undid local form change')}});bind('prepare-generation','click',()=>confirm({action:'start_generation',message:'Confirm destination '+(selected()?.dataset.etsy||'')+' before creating an unpublished Printify draft.'}));bind('open-chat','click',()=>q('chat').classList.add('open'));bind('close-chat','click',()=>q('chat').classList.remove('open'));"
        "let savedLayout=null,customizing=false,dragPanel=null;const panelNodes=()=>[...document.querySelectorAll('.layout-panel')];function clampChat(value){return Math.max(300,Math.min(value,window.innerWidth*.55))}function applyLayout(layout){savedLayout=structuredClone(layout);q('theme-chooser').value=layout.theme_id;if(window.innerWidth>800)document.documentElement.style.setProperty('--chat-width',clampChat(layout.shell.chat_width)+'px');const byId=Object.fromEntries(layout.panels.map(x=>[x.panel_id,x]));panelNodes().forEach(panel=>{const item=byId[panel.dataset.panelId];if(!item)return;panel.style.setProperty('--panel-column',item.column);panel.style.setProperty('--panel-row',item.row);panel.style.setProperty('--panel-width',item.width);panel.style.setProperty('--panel-height',item.height);panel.hidden=item.layout_locked?false:item.hidden;panel.dataset.layoutLocked=String(item.layout_locked);const lock=panel.querySelector('.panel-title span');if(lock)lock.textContent=item.layout_locked?'🔒':''})}async function loadLayout(view){try{const response=await fetch('/app/layouts/'+encodeURIComponent(view),{cache:'no-store'});if(response.ok)applyLayout(await response.json())}catch(e){reportInitError()}}function currentLayout(){const layout=structuredClone(savedLayout);layout.theme_id=q('theme-chooser').value;layout.shell.chat_width=Math.round(clampChat(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--chat-width'))||420));if(window.innerWidth<=800)layout.shell.chat_width=savedLayout.shell.chat_width;const width=Math.max(1,q('generic-view').parentElement.clientWidth);panelNodes().forEach(panel=>{const item=layout.panels.find(x=>x.panel_id===panel.dataset.panelId);if(!item||item.layout_locked)return;item.column=Math.max(1,Math.min(12,parseInt(getComputedStyle(panel).getPropertyValue('--panel-column'))||1));item.row=Math.max(1,Math.min(100,parseInt(getComputedStyle(panel).getPropertyValue('--panel-row'))||1));item.width=Math.max(1,Math.min(12,Math.round(panel.clientWidth/width*12)));if(item.column+item.width-1>12)item.width=13-item.column;item.height=Math.max(1,Math.min(50,Math.round(panel.clientHeight/48)));item.hidden=panel.hidden});return layout}function customize(on){customizing=on;document.body.classList.toggle('customizing',on);const toolbar=q('layout-toolbar'),button=q('customize-layout');if(toolbar)toolbar.hidden=!on;if(button)button.hidden=on;panelNodes().forEach(panel=>panel.draggable=on&&panel.dataset.layoutLocked!=='true')}bind('customize-layout','click',()=>customize(true));bind('cancel-layout','click',()=>{if(savedLayout)applyLayout(savedLayout);customize(false)});bind('save-layout','click',async()=>{const response=await fetch('/app/layouts/'+encodeURIComponent(activeView),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...currentLayout(),csrf_token:csrf})});if(response.ok){applyLayout(await response.json());customize(false);log('Saved layout')}else q('chat-state').textContent='Layout could not be saved.'});bind('reset-layout','click',async()=>{const response=await fetch('/app/layouts/'+encodeURIComponent(activeView),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf})});if(response.ok){applyLayout(await response.json());customize(false);log('Reset layout')}});const divider=q('shell-divider');if(divider){divider.onpointerdown=event=>{if(window.innerWidth<=800)return;divider.setPointerCapture(event.pointerId);divider.classList.add('dragging')};divider.onpointermove=event=>{if(!divider.hasPointerCapture(event.pointerId)||window.innerWidth<=800)return;document.documentElement.style.setProperty('--chat-width',clampChat(event.clientX)+'px')};divider.onpointerup=event=>{if(divider.hasPointerCapture(event.pointerId))divider.releasePointerCapture(event.pointerId);divider.classList.remove('dragging')}}panelNodes().forEach(panel=>{const title=panel.querySelector('.panel-title');if(title)title.onmousedown=()=>panel.dataset.dragHandle='true';panel.ondragstart=event=>{if(!customizing||panel.dataset.layoutLocked==='true'||panel.dataset.dragHandle!=='true'){event.preventDefault();return}dragPanel=panel};panel.ondragend=()=>{panel.dataset.dragHandle='false';dragPanel=null};panel.ondragover=event=>{if(customizing&&dragPanel&&panel.dataset.layoutLocked!=='true')event.preventDefault()};panel.ondrop=event=>{event.preventDefault();if(!dragPanel||panel.dataset.layoutLocked==='true'||dragPanel.dataset.layoutLocked==='true')return;const col=panel.style.getPropertyValue('--panel-column'),row=panel.style.getPropertyValue('--panel-row');panel.style.setProperty('--panel-column',dragPanel.style.getPropertyValue('--panel-column'));panel.style.setProperty('--panel-row',dragPanel.style.getPropertyValue('--panel-row'));dragPanel.style.setProperty('--panel-column',col);dragPanel.style.setProperty('--panel-row',row)}});const baseNavigate=navigate;navigate=view=>{baseNavigate(view);loadLayout(view)};loadLayout(activeView);"
        "let dockInteracting=false,pendingDockState=null,lastDockKey='',jobNavigationState={stage:'',ready:false,failed:false,pending:false};const dock=q('context-items'),dockShell=q('context-dock'),lockedDock=initialNavigation.filter(item=>item.locked);function contextItems(){const items=[];const add=item=>{if(!items.some(x=>x.view_id===item.view_id)&&!lockedDock.some(x=>x.view_id===item.view_id))items.push(item)};if(selectedJob){if(jobNavigationState.failed)add({item_id:'job-diagnostics',label:'Diagnostics',view_id:'diagnostics',locked:false,badge:'warning'});else if(jobNavigationState.ready)add({item_id:'job-review',label:'Review',view_id:'commerce.review',locked:false,badge:'ready'});else if(jobNavigationState.pending)add({item_id:'job-approval',label:'Review',view_id:'commerce.review',locked:false,badge:'pending_approval'});else add({item_id:'current-job',label:'Current job',view_id:'commerce.loading',locked:false,badge:'progress'})}if(!lockedDock.some(x=>x.view_id===activeView))add({item_id:'active-workspace',label:activeView.replaceAll('.',' '),view_id:activeView,locked:false,badge:null});return [lockedDock[0],...items,lockedDock[1],lockedDock[2]]}function renderDock(items){dock.replaceChildren(...items.map(item=>{const button=document.createElement('button');button.type='button';button.dataset.view=item.view_id;button.dataset.navId=item.item_id;button.dataset.locked=String(item.locked);button.append(document.createTextNode(item.label));if(item.badge){const badge=document.createElement('span');badge.className='dock-badge '+item.badge;badge.textContent=item.badge.replaceAll('_',' ');button.append(badge)}return button}))}function recalculateDock(){const state={activeView,selectedJob,...jobNavigationState},key=JSON.stringify(state);if(key===lastDockKey)return;if(dockInteracting){pendingDockState=key;return}lastDockKey=key;renderDock(contextItems())}dockShell.addEventListener('pointerdown',()=>{dockInteracting=true});document.addEventListener('pointerup',()=>{dockInteracting=false;if(pendingDockState){pendingDockState=null;recalculateDock()}});dockShell.addEventListener('click',event=>{const button=event.target.closest('button[data-view]');if(button)navigate(button.dataset.view)});const dockNavigate=navigate;navigate=view=>{dockNavigate(view);const agencyWorkspace=view==='agency.home'||view==='agency.book-scout';q('agency-view').hidden=!agencyWorkspace;q('admin-view').hidden=view!=='admin.home';q('dashboard-view').hidden=view!=='dashboard';if(agencyWorkspace||view==='admin.home'||view==='dashboard'){q('commerce-new').hidden=true;q('generic-view').hidden=true}if(view==='agency.book-scout'&&typeof openAgencySection==='function')openAgencySection('book-scout');else if(view==='agency.home'&&typeof openAgencySection==='function')openAgencySection('my-agents');recalculateDock()};window.addEventListener('popstate',()=>{const view=new URLSearchParams(location.search).get('view')||'dashboard';if(allowedViews.includes(view))navigate(view)});watchJob=async function(){if(!selectedJob)return;try{const response=await fetch('/commerce/jobs/'+encodeURIComponent(selectedJob)+'/status.json',{cache:'no-store'}),status=await response.json(),next={stage:status.stage||'',ready:Boolean(status.ready_for_review),failed:Boolean(status.failed),pending:String(status.stage||'').includes('approval')};if(JSON.stringify(next)!==JSON.stringify(jobNavigationState)){jobNavigationState=next;recalculateDock()}q('job-status').textContent=status.progress_label||status.stage;if(status.ready_for_review){navigate('commerce.review');return}if(status.failed){navigate('diagnostics');q('generic-copy').textContent=status.failure_message_safe||'Product preparation did not complete.';return}setTimeout(watchJob,1500)}catch(e){setTimeout(watchJob,2500)}};navigate(activeView);"
        "let healthState='';async function pollHealth(){try{const response=await fetch('/app/health',{cache:'no-store'});if(!response.ok)throw new Error();const value=await response.json();if(value.state!==healthState){healthState=value.state;const dot=q('health-dot');if(dot){dot.className='health-dot '+value.state;dot.setAttribute('aria-label','System health: '+value.label)}const label=q('health-label'),systems=q('health-systems');if(label)label.textContent=value.label;if(systems)systems.replaceChildren(...value.systems.map(system=>{const item=document.createElement('li');item.textContent=system.label+': '+system.status+' — '+system.message;return item}))}}catch(e){if(healthState!=='red'){healthState='red';const dot=q('health-dot'),label=q('health-label');if(dot){dot.className='health-dot red';dot.setAttribute('aria-label','System health: API/server unavailable')}if(label)label.textContent='A required local subsystem is unavailable'}}setTimeout(pollHealth,15000)}bind('health-dot','click',()=>{const panel=q('health-detail'),dot=q('health-dot');if(!panel||!dot){reportInitError();return}const open=panel.hidden;panel.hidden=!open;dot.setAttribute('aria-expanded',String(open))});pollHealth();"
        "async function loadAccessStatus(){try{const response=await fetch('/app/access-status',{cache:'no-store'});if(!response.ok)throw new Error();const value=await response.json();q('access-mode').textContent=value.access_mode;q('access-host').textContent=value.trusted_hostname;q('access-https').textContent=value.https?'HTTPS':'plain HTTP';q('access-connection').textContent=value.connection_type;q('access-scope').textContent=value.access_scope;q('access-warning').hidden=!value.warning;q('access-warning').textContent=value.warning||''}catch(e){const mode=q('access-mode'),warning=q('access-warning');if(mode)mode.textContent='unavailable';if(warning){warning.hidden=false;warning.textContent='Access status is unavailable.'}}}loadAccessStatus();document.documentElement.dataset.jamesosReady='true';"
        "});</script></body></html>")
    replacements={
        "<div id='confirmations' data-component='confirmation'></div><textarea id='chat-message'":"<div id='attachments' aria-live='polite'></div><textarea id='chat-message'",
        "<div class='chat-actions' data-component='action_bar'><button type='button' id='send'>Send</button><button type='button' id='stop' disabled>Stop</button><button type='button' id='retry' disabled>Retry</button><button type='button' id='reset'>Reset</button></div>":"<div class='chat-actions' data-component='action_bar'><button type='button' id='send'>Send</button><label id='upload-control' class='button' for='attachment-input' role='button' tabindex='0' title='Attach files'>📎 Upload</label><input id='attachment-input' type='file' multiple hidden accept='.txt,.md,.markdown,.json,.csv,.pdf,.png,.jpg,.jpeg,.webp'><button type='button' id='reset'>Reset conversation</button></div>",
        "<div class='activity-actions'><strong>Activity</strong><button type='button' id='undo' disabled>Undo</button></div>":"<div class='activity-actions'><strong>Activity</strong></div>",
        "<header class='panel-title'>Commerce Creator <span></span></header>":"<header class='panel-title'>Product Studio <span></span></header>",
        "<input type='hidden' name='destination_confirmed' value='true'><button type='button' id='prepare-generation'>":"<input type='hidden' name='destination_confirmed' value='true'><div id='confirmations' data-component='confirmation'></div><button type='button' id='prepare-generation'>",
        "<aside class='layout-panel' data-panel-id='external_confirmation' data-component='confirmation' data-layout-locked='true'><header class='panel-title'>External action confirmation <span>🔒</span></header><div class='panel-content'>Provider actions require explicit confirmation.</div></aside>":"",
        "<section id='agency-view' hidden><h3>The Agency</h3><div class='layout-grid'>":"<section id='agency-view' hidden><h3>The Agency</h3><div class='layout-grid agency-registry' id='agency-registry'><article class='layout-panel'><header class='panel-title'>The Merchant <span></span></header><div class='panel-content'><p>Build and review commerce products locally without contacting a provider.</p><button type='button' data-view='commerce.new'>Open Product Studio</button></div></article>",
        "<article class='layout-panel'><header class='panel-title'>Agent tools <span></span></header><div class='panel-content'>Registered tools appear here.</div></article>":"",
    }
    for old,new in replacements.items():page=page.replace(old,new)
    page=page.replace("Your local workspace assistant","Chat with Jade")
    page=page.replace("<button type='button' id='reset'>Reset conversation</button>","<button type='button' id='reset'>Clear</button><div class='private-settings'><label><input type='checkbox' id='private-chat'> Private chat</label><small>This conversation is not saved or added to memory.</small><label><input type='checkbox' id='adult-mode' disabled> Adult mode (18+)</label><small>Allows consensual adult conversation and fictional roleplay.</small></div><strong id='private-indicator' class='dock-badge warning' hidden>Private chat — ephemeral</strong><small id='private-note' hidden>Earlier normal conversations are not deleted.</small><dialog id='adult-confirm'><p><strong>Adult mode is for adults 18 and older.</strong></p><p>It allows mature and explicit conversation involving consenting adults. It does not allow content involving minors, coercion, exploitation, or illegal sexual abuse.</p><button type='button' id='adult-affirm'>I am 18 or older — Enable</button> <button type='button' id='adult-cancel'>Cancel</button></dialog>")
    page=page.replace("</style>",".private-settings{display:grid;gap:.2rem;margin:.45rem 0}.private-settings small{margin-left:1.5rem}dialog{max-width:34rem;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:.7rem}</style>",1)
    page=re.sub(r"<span id='identity'>Profile: .*?</span>","",page,count=1)
    page=page.replace("<button type='button' id='reset-layout'>Reset</button>","<button type='button' id='reset-layout'>Restore default layout</button>")
    page=page.replace(".agency-registry>.layout-panel{grid-column:auto;grid-row:auto}",".agency-registry{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:.9rem}.agency-registry>.layout-panel{grid-column:auto!important;grid-row:auto!important;min-width:280px}.agency-registry>.layout-panel:first-child{grid-column:1/-1!important}")
    page=page.replace("</style>",".agency-tabs{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem}.agent-card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}.agent-card{border:1px solid var(--line);border-radius:.7rem;background:var(--surface);padding:1rem;min-width:0}.agent-card p{overflow-wrap:anywhere}.agency-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin-bottom:1rem}.agency-summary .agent-card{text-align:center}.agency-section[hidden]{display:none!important}</style>",1)
    summary=agency_snapshot["summary"]
    summary_html="".join(f"<article class='agent-card'><strong>{html_escape(label)}</strong><p>{int(summary[key])}</p></article>" for key,label in (("installed_agents","Installed agents"),("running_now","Running now"),("waiting_for_approval","Waiting for approval"),("degraded_agents","Degraded agents"),("updates_available","Updates available")))
    agent_cards=[]
    for agent in agency_snapshot["agents"]:
        aid=html_escape(agent["agent_id"],quote=True);workspace=agent["workspace"];open_label="Open Product Studio" if workspace=="commerce.new" else "Open Admin" if workspace=="admin.home" else "Open Scout" if workspace=="agency.book-scout" else "Open Producer" if workspace=="agency.coloring-book-producer" else "Open Home"
        actions=f"<button type='button' data-view='{html_escape(workspace,quote=True)}'>{open_label}</button> <button type='button' data-agent-detail='{aid}'>View details</button>"
        if agent["disable_allowed"]:actions+=f" <button type='button' data-agent-action='disable' data-agent-id='{aid}'>Disable</button>"
        if agent["removable"]:actions+=f" <button type='button' data-agent-action='remove' data-agent-id='{aid}'>Remove</button>"
        agent_cards.append(f"<article class='agent-card' data-agent-card='{aid}'><h4>{html_escape(agent['name'])}</h4><p>{html_escape(agent['role'])}</p><p><strong>{html_escape(agent['installation_state'].title())} · {html_escape(agent['enabled_state'].title())} · {html_escape(agent['runtime_state'].title())}</strong></p><p>Version: {html_escape(str(agent['installed_version']))} · Update: {html_escape(agent['update_state'])}</p><p>Capabilities: {html_escape(', '.join(agent['capabilities']))}</p><p>Permissions: {html_escape(', '.join(agent['permissions']))}</p><p>Workspace: {html_escape(workspace)}</p>{actions}</article>")
    marketplace=[]
    for item in agency_snapshot["catalog"]:
        permissions=" · ".join((f"Filesystem: {item['filesystem_access']}",f"Network: {item['network_access']}",f"Provider: {item['provider_access']}",f"Credentials: {item['credential_access']}",f"Terminal: {item['terminal_access']}"))
        if item["implementation_state"]=="implemented":
            action="<button type='button' disabled>Installed</button>" if item.get("installed") else f"<button type='button' data-agent-action='install' data-agent-id='{html_escape(item['agent_id'],quote=True)}'>Install / Hire</button>"
        else:action="<button type='button' disabled>Planned</button>"
        marketplace.append(f"<article class='agent-card' data-marketplace-agent='{html_escape(item['agent_id'],quote=True)}'><h4>{html_escape(item['name'])}</h4><p>{html_escape(item.get('category') or 'Utility')} · {html_escape(item['publisher'])} · {html_escape(item['version'])} · {'Verified' if item['verified'] else 'Unverified'}</p><p>{html_escape(item['description'])}</p><details data-layout-locked='true'><summary>Permission review</summary><p>{html_escape(permissions)}</p><p>Confirmation: {html_escape(', '.join(item['confirmation_requirements']))}</p></details>{action}</article>")
    running_html="<p>No agents are currently running.</p>" if not agency_snapshot["running_now"] else "".join(f"<article class='agent-card'><strong>{html_escape(item['agent_id'])}</strong><p>{html_escape(item['operation'])} · {html_escape(item['stage'])}</p><p>Provider contacted: {'yes' if item['provider_contacted'] else 'no'} · Waiting for approval: {'yes' if item['waiting_for_approval'] else 'no'}</p></article>" for item in agency_snapshot["running_now"])
    scout_workspace=("<section class='agency-section layout-panel' data-agency-section='book-scout' data-panel-id='book_scout_workspace' data-component='card' data-layout-locked='false' id='book-scout-workspace' hidden><h4>Book Opportunity Scout</h4><p>DEMO evidence is deterministic; LIVE uses only public, read-only sources. This agent does not generate or publish books.</p>"
        "<form id='book-scout-form'><label>Market <input name='market' value='US' required></label><label>Audience <input name='audience' value='children ages 4–8' required></label><label>Book type <input name='book_type' value='coloring book' required></label><label>Research mode <select name='source_mode'><option value='demo'>Demo</option><option value='manual'>Manual</option><option value='live'>Live</option></select></label><label>Candidate count <input name='candidate_count' type='number' min='5' max='100' value='20' required></label><label>Result count <input name='result_count' type='number' min='1' max='20' value='5' required></label><button type='submit'>Run Scout</button></form><p id='book-scout-status' aria-live='polite'></p><div id='book-scout-live-summary'></div><div id='book-scout-results'></div><h4>Run history</h4><div id='book-scout-history'>No research runs yet.</div><button type='button' data-agency-tab='my-agents'>Back to My Agents</button></section>")
    producer_workspace=("<section class='agency-section layout-panel' data-agency-section='coloring-book-producer' data-panel-id='coloring_book_projects' id='coloring-book-producer-workspace' hidden><h4>Coloring Book Producer</h4><p>Local planning projects only. No images, PDFs, provider writes, publication, purchase, or order.</p><p id='coloring-book-status' aria-live='polite'></p><div id='coloring-book-projects'>No local projects yet.</div><div id='coloring-book-project'></div><button type='button' data-agency-tab='my-agents'>Back to My Agents</button></section>")
    agency_html=("<section id='agency-view' hidden><h3>The Agency</h3><nav class='agency-tabs' aria-label='Agency sections'>"+"".join(f"<button type='button' data-agency-tab='{key}'>{label}</button>" for key,label in (("my-agents","My Agents"),("marketplace","Marketplace"),("runs","Runs"),("approvals","Approvals"),("updates","Updates")))+"</nav>"
        f"<section class='agency-section' data-agency-section='my-agents'><div class='agency-summary'>{summary_html}</div><h4>My Agents</h4><div class='agent-card-grid' id='agency-registry'>{''.join(agent_cards)}</div><h4>Running now</h4><div id='agency-running'>{running_html}</div><h4>Needs attention</h4><p>No agent-management issues need attention.</p><h4>Recent runs</h4><p>No recent agent runs.</p></section>"
        f"<section class='agency-section' data-agency-section='marketplace' hidden><h4>Local curated marketplace</h4><p>No remote code is downloaded or executed.</p><div class='agent-card-grid'>{''.join(marketplace)}</div></section>"
        f"<section class='agency-section' data-agency-section='runs' hidden><h4>Runs</h4><div>{running_html}</div></section>"
        "<section class='agency-section' data-agency-section='approvals' data-layout-locked='true' hidden><h4>Approvals 🔒</h4><p>No protected agent actions are waiting for review. Requesting agents cannot approve their own actions.</p></section>"
        "<section class='agency-section' data-agency-section='updates' hidden><h4>Updates</h4><p>All installed agents are current. Updates are never automatic; permission increases require confirmation.</p></section>"
        +scout_workspace+producer_workspace+"<section class='agency-section' id='agency-agent-detail' data-layout-locked='true' hidden><h4>Agent details</h4><div id='agency-agent-detail-content'></div><button type='button' data-agency-tab='my-agents'>Back to My Agents</button></section></section>")
    old_agency=re.search(r"<section id='agency-view' hidden>.*?</section><section id='admin-view'",page).group(0);page=page.replace(old_agency,agency_html+"<section id='admin-view'",1)
    page=page.replace("undoStack=[],lastMessage='',controller=null,applyingProfile=false", "attachments=[],chatActive=false,composing=false,privateMode=false,adultMode=false,adultConsentSession='',adultAvailable="+str(private_policy["adult_mode_available"]).lower()+",applyingProfile=false")
    page=page.replace(";q('undo').disabled=!undoStack.length", "")
    page=page.replace("function change(mutator,label){undoStack.push(snapshot());mutator();identity();log(label)}", "function change(mutator,label){mutator();identity();log(label)}")
    page=page.replace("const before=snapshot();profileSelect.value=profileId", "profileSelect.value=profileId").replace("if(record){undoStack.push(before);log(", "if(record){log(")
    page=page.replace("'diagnostics':'Diagnostics'}", "'diagnostics':'Diagnostics','agency.home':'The Agency','agency.agent':'Agent details','admin.home':'Admin'}")
    page=page.replace("if(!allowedViews.includes(view))return;activeView=view", "if(typeof view!=='string'||!allowedViews.includes(view))return;const title=({'dashboard':'Home','agency.home':'The Agency','agency.agent':'Agent details','agency.book-scout':'Book Opportunity Scout','admin.home':'Admin','commerce.new':'Product Studio','commerce.loading':'Generating product','commerce.review':'Product review','commerce.diagnostics':'Commerce diagnostics','commerce.published':'Published product','jobs.list':'Jobs','jobs.detail':'Job detail','profiles':'Profiles','settings':'Settings','diagnostics':'Diagnostics'})[view];if(!title)return;const enteringProduct=view==='commerce.new'&&activeView!=='commerce.new';if(enteringProduct){q('listing_title').value='';fieldMeta.listing_title={dirty:false,autoValue:''}}activeView=view")
    page=page.replace("log('Opened '+titles[view])", "log('Opened '+title)")
    page=page.replace("'agency.book-scout':'Book Opportunity Scout','admin.home'", "'agency.book-scout':'Book Opportunity Scout','agency.coloring-book-producer':'Coloring Book Producer','admin.home'")
    page=page.replace("view==='agency.home'||view==='agency.book-scout'", "view==='agency.home'||view==='agency.book-scout'||view==='agency.coloring-book-producer'")
    page=page.replace("if(view==='agency.book-scout'&&typeof openAgencySection==='function')openAgencySection('book-scout')", "if(view==='agency.book-scout'&&typeof openAgencySection==='function')openAgencySection('book-scout');else if(view==='agency.coloring-book-producer'&&typeof openAgencySection==='function')openAgencySection('coloring-book-producer')")
    page=page.replace("history.replaceState(null,'','/app?view='+encodeURIComponent(view));log('Opened '+title)","history.replaceState(null,'','/app?view='+encodeURIComponent(view));if(view==='admin.home'&&typeof loadChatDiagnostics==='function')loadChatDiagnostics();log('Opened '+title)")
    page=page.replace("history.replaceState(null,'','/app?view='+encodeURIComponent(view));if(view==='admin.home'", "const nextUrl='/app?view='+encodeURIComponent(view)+(selectedJob?'&job_id='+encodeURIComponent(selectedJob):'');if(new URL(location.href).searchParams.get('view')===view)history.replaceState(null,'',nextUrl);else history.pushState(null,'',nextUrl);if(view==='admin.home'")
    page=page.replace("p.textContent=command.message;let yes", "p.textContent='Requested action: '+command.action.replaceAll('_',' ')+'. Destination/resource: '+(selected()?.dataset.etsy||'current workspace')+'. External provider contacted: '+(command.action==='request_revision'?'no':'yes')+'. Irreversible publication/submission: '+(command.action==='publish'?'yes':'no')+'. '+command.message;let yes")
    old_send="async function send(){const message=q('chat-message').value.trim();if(!message)return;lastMessage=message;q('retry').disabled=true;q('send').disabled=true;q('stop').disabled=false;q('chat-state').textContent='Thinking…';turns.push({role:'user',text:message});renderTurns();controller=new AbortController();try{const x=selected(),response=await fetch('/app/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({csrf_token:csrf,conversation_id:conversation,message,active_view:activeView,active_profile_id:x?.value||'',selected_job_id:selectedJob,form:formState()})});let data={};try{data=await response.json()}catch(e){}if(!response.ok)throw new Error(data.message||'JamesOS could not complete the request.');turns.push({role:'assistant',text:data.message});(data.warnings||[]).forEach(x=>turns.push({role:'assistant',text:'Warning: '+x}));renderTurns();execute(data.commands||[]);q('chat-message').value='';q('chat-state').textContent='Ready.'}catch(e){if(e.name!=='AbortError'){turns.push({role:'assistant',text:'Safe error: '+(e.message||'Request failed.')});renderTurns()}q('chat-state').textContent=e.name==='AbortError'?'Stopped.':'Safe error.';q('retry').disabled=false}finally{controller=null;q('send').disabled=false;q('stop').disabled=true}}bind('send','click',send);bind('stop','click',()=>controller?.abort());bind('retry','click',()=>{q('chat-message').value=lastMessage;send()});"
    new_send="function sizeLabel(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(1)+' MB'}function renderAttachments(){const node=q('attachments');if(!node)return;node.replaceChildren(...attachments.map(item=>{const row=document.createElement('div'),text=document.createElement('span'),remove=document.createElement('button');text.textContent=item.filename+' · '+item.content_type+' · '+sizeLabel(item.size);remove.type='button';remove.textContent='Remove';remove.onclick=()=>{attachments=attachments.filter(x=>x.attachment_id!==item.attachment_id);renderAttachments()};row.append(text,remove);return row}))}async function uploadFiles(files){for(const file of files){const form=new FormData();form.append('csrf_token',csrf);form.append('conversation_id',conversation);form.append('file',file);try{const response=await fetch('/app/attachments',{method:'POST',body:form}),data=await response.json();if(!response.ok)throw new Error(data.detail||'Attachment rejected.');attachments.push(data);renderAttachments()}catch(e){q('chat-state').textContent=e.message||'Attachment rejected.'}}q('attachment-input').value=''}async function send(){const input=q('chat-message'),message=input.value.trim();if(!message||chatActive||composing)return;chatActive=true;q('send').disabled=true;q('chat-state').textContent='Thinking…';turns.push({role:'user',text:message});renderTurns();try{const x=selected(),response=await fetch('/app/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:conversation,message,active_view:activeView,active_profile_id:x?.value||'',selected_job_id:selectedJob,form:formState(),attachments})});let data={};try{data=await response.json()}catch(e){}if(!response.ok)throw new Error(data.message||data.detail||'JamesOS could not complete the request.');turns.push({role:'assistant',text:data.message});(data.warnings||[]).forEach(x=>turns.push({role:'assistant',text:'Warning: '+x}));renderTurns();execute(data.commands||[]);input.value='';attachments=[];renderAttachments();q('chat-state').textContent='Ready.'}catch(e){turns.push({role:'assistant',text:'Safe error: '+(e.message||'Request failed. You can edit and send another message.')) ;renderTurns();q('chat-state').textContent='Request failed safely.'}finally{chatActive=false;q('send').disabled=false}}bind('send','click',send);bind('attachment-input','change',event=>uploadFiles(event.target.files));bind('chat-message','compositionstart',()=>composing=true);bind('chat-message','compositionend',()=>composing=false);bind('chat-message','keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&!composing){event.preventDefault();send()}});"
    page=page.replace(old_send,new_send)
    page=page.replace("finally{chatActive=false;q('send').disabled=false}","finally{await loadChatDiagnostics();chatActive=false;q('send').disabled=false}")
    page=page.replace("Request failed. You can edit and send another message.')) ;", "Request failed. You can edit and send another message.')});")
    page=page.replace("if(!response.ok)throw new Error(data.message||data.detail||'JamesOS could not complete the request.');turns.push", "if(!response.ok){if(response.status===403&&adultMode){adultMode=false;adultConsentSession='';q('adult-mode').checked=false;q('adult-mode').disabled=true}throw new Error(data.message||data.detail||'JamesOS could not complete the request.')}turns.push")
    page=page.replace("remove.onclick=()=>{attachments=attachments.filter(x=>x.attachment_id!==item.attachment_id);renderAttachments()}", "remove.onclick=async()=>{const response=await fetch('/app/attachments/'+encodeURIComponent(item.attachment_id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:conversation})});if(response.ok){attachments=attachments.filter(x=>x.attachment_id!==item.attachment_id);renderAttachments()}else q('chat-state').textContent='Attachment could not be removed safely.'}")
    page=page.replace("text.textContent=item.filename+' · '+item.content_type+' · '+sizeLabel(item.size);", "text.textContent=(item.state==='processing'?'Processing: ':'Attached: ')+item.filename+(item.state==='processing'?'':' — ready to send')+' · '+item.content_type+' · '+sizeLabel(item.size);")
    page=page.replace("q('transcript').appendChild(p)});", "q('transcript').appendChild(p);(t.attachments||[]).forEach(a=>{const card=document.createElement('div');card.className='attachment-receipt';card.textContent='Processed: '+a.filename+' · '+a.content_type+' · '+sizeLabel(a.byte_count||a.size)+' · '+a.ingestion_state;q('transcript').appendChild(card)})});")
    page=page.replace("turns.push({role:'user',text:message});renderTurns();", "attachments.forEach(item=>item.state='processing');renderAttachments();const userTurn={role:'user',text:message,attachments:[]};turns.push(userTurn);renderTurns();")
    page=page.replace("selected_job_id:selectedJob,form:formState(),attachments})", "selected_job_id:selectedJob,form:formState(),attachments:attachments.map(({attachment_id,filename,content_type,size})=>({attachment_id,filename,content_type,size}))})")
    page=page.replace("selected_job_id:selectedJob,form:formState(),attachments:attachments.map", "selected_job_id:selectedJob,ephemeral:privateMode,private_mode:privateMode,adult_mode:adultMode,adult_consent_session:adultConsentSession,form:formState(),attachments:attachments.map")
    page=page.replace("q('identity').textContent='Profile: '+x.dataset.brand;","")
    page=page.replace("(data.warnings||[]).forEach(x=>turns.push({role:'assistant',text:'Warning: '+x}));renderTurns();", "(data.warnings||[]).forEach(x=>turns.push({role:'assistant',text:'Warning: '+x}));userTurn.attachments=data.attachment_receipts||[];renderTurns();")
    page=page.replace("}catch(e){turns.push({role:'assistant',text:'Safe error: '", "}catch(e){attachments.forEach(item=>item.state='attached');renderAttachments();turns.push({role:'assistant',text:'Safe error: '")
    page=page.replace("bind('attachment-input','change',event=>uploadFiles(event.target.files));", "bind('attachment-input','change',event=>uploadFiles(event.target.files));bind('upload-control','keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();q('attachment-input').click()}});")
    page=page.replace("undoStack=[];renderTurns();q('activity').replaceChildren();q('undo').disabled=true;", "attachments=[];renderAttachments();renderTurns();q('activity').replaceChildren();")
    page=page.replace("bind('reset','click',()=>{conversation=crypto.randomUUID();localStorage.setItem('jamesos-conversation-id',conversation);turns=[];activity=[];attachments=[];renderAttachments();renderTurns();q('activity').replaceChildren();q('chat-state').textContent='Conversation reset.'})", "bind('reset','click',async()=>{const pending=[...attachments],oldConversation=conversation;await Promise.all(pending.map(item=>fetch('/app/attachments/'+encodeURIComponent(item.attachment_id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:oldConversation})}).catch(()=>null)));conversation=crypto.randomUUID();localStorage.setItem('jamesos-conversation-id',conversation);turns=[];activity=[];attachments=[];renderAttachments();renderTurns();q('activity').replaceChildren();q('chat-state').textContent='Conversation reset.'})")
    page=page.replace("await Promise.all(pending.map(item=>fetch('/app/attachments/'+encodeURIComponent(item.attachment_id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:oldConversation})}).catch(()=>null)));conversation=", "const removed=await Promise.all(pending.map(item=>fetch('/app/attachments/'+encodeURIComponent(item.attachment_id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:oldConversation})}).then(async response=>response.ok&&Boolean((await response.json()).removed)).catch(()=>false)));if(removed.some(value=>!value)){q('chat-state').textContent='Pending attachments could not be removed; conversation was not reset.';return}conversation=")
    page=page.replace("bind('undo','click',()=>{const s=undoStack.pop();if(s){restore(s);log('Undid local form change')}});", "")
    privacy_js="""async function discardPending(){const old=conversation,pending=[...attachments];const results=await Promise.all(pending.map(item=>fetch('/app/attachments/'+encodeURIComponent(item.attachment_id),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,conversation_id:old})}).then(r=>r.ok).catch(()=>false)));if(results.some(ok=>!ok)){q('chat-state').textContent='Pending attachments could not be removed; mode was not changed.';return false}attachments=[];renderAttachments();return true}bind('private-chat','change',async event=>{if(!await discardPending()){event.target.checked=privateMode;return}privateMode=event.target.checked;adultMode=false;adultConsentSession='';q('adult-mode').checked=false;q('adult-mode').disabled=!privateMode||!adultAvailable;conversation=crypto.randomUUID();turns=[];renderTurns();q('private-indicator').hidden=!privateMode;q('private-note').hidden=!privateMode;if(privateMode)localStorage.removeItem('jamesos-conversation-id');else localStorage.setItem('jamesos-conversation-id',conversation);q('chat-state').textContent=privateMode?'Private chat started. Nothing from this chat is saved to memory.':'New normal conversation started.'});bind('adult-mode','change',async event=>{if(!event.target.checked){if(!await discardPending()){event.target.checked=true;return}adultMode=false;adultConsentSession='';conversation=crypto.randomUUID();turns=[];renderTurns();return}event.target.checked=false;if(!privateMode||!adultAvailable)return;q('adult-confirm').showModal()});bind('adult-cancel','click',()=>{q('adult-mode').checked=false;q('adult-confirm').close()});bind('adult-affirm','click',async()=>{if(!await discardPending())return;const response=await fetch('/app/private-session/affirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,affirmed_18_plus:true})}),value=await response.json();if(response.ok){adultConsentSession=value.adult_consent_session;adultMode=true;q('adult-mode').checked=true;conversation=crypto.randomUUID();turns=[];renderTurns();localStorage.removeItem('jamesos-conversation-id');q('chat-state').textContent='Adult mode enabled for this private session.'}q('adult-confirm').close()});q('adult-mode').disabled=true;"""
    page=page.replace("bind('open-chat','click'", privacy_js+"bind('open-chat','click'")
    page=page.replace("conversation=crypto.randomUUID();localStorage.setItem('jamesos-conversation-id',conversation);turns=[]", "conversation=crypto.randomUUID();if(privateMode)localStorage.removeItem('jamesos-conversation-id');else localStorage.setItem('jamesos-conversation-id',conversation);turns=[]")
    page=page.replace("bind('reset','click',async()=>{", "bind('reset','click',async()=>{if(adultConsentSession)await fetch('/app/private-session/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,adult_consent_session:adultConsentSession})}).catch(()=>null);adultMode=false;adultConsentSession='';q('adult-mode').checked=false;")
    dashboard="""<section id='dashboard-view' class='layout-grid'><article class='layout-panel' data-panel-id='system_overview'><header class='panel-title'>System overview <span></span></header><div class='panel-content'><p id='dashboard-summary'>Loading local status…</p><ul id='dashboard-systems'></ul></div></article><article class='layout-panel' data-panel-id='work_in_progress'><header class='panel-title'>Work in progress <span></span></header><div class='panel-content' id='dashboard-work'>Loading jobs…</div></article><article class='layout-panel' data-panel-id='recent_workspaces'><header class='panel-title'>Recent workspaces <span></span></header><div class='panel-content'><button type='button' data-view='commerce.new'>Product Studio</button> <button type='button' data-view='agency.home'>The Agency</button> <button type='button' data-view='admin.home'>Admin</button></div></article><article class='layout-panel' data-panel-id='quick_actions'><header class='panel-title'>Quick actions <span></span></header><div class='panel-content'><button type='button' data-view='commerce.new'>Open Product Studio</button> <button type='button' data-view='agency.home'>Open The Agency</button> <button type='button' data-view='admin.home'>Open Admin</button> <button type='button' data-view='jobs.list'>View failed jobs</button> <button type='button' id='new-conversation'>Start a new conversation</button></div></article><article class='layout-panel' data-panel-id='recent_results'><header class='panel-title'>Recent results <span></span></header><div class='panel-content' id='dashboard-results'>No recent results.</div></article></section>"""
    admin="""<section id='admin-view' hidden><h3>Admin</h3><div class='layout-grid'><article class='layout-panel' data-panel-id='admin_services'><header class='panel-title'>Services <span></span></header><div class='panel-content'>JamesOS · Ollama · GPU · ComfyUI · storage readiness<br><small>Restart controls are available only through approved registered operations.</small></div></article><article class='layout-panel' data-panel-id='provider_credentials' data-layout-locked='true'><header class='panel-title'>Provider credentials <span>🔒</span></header><div class='panel-content' id='credential-controls'><form data-provider='printify'><label>Printify API key <input type='password' name='secret' autocomplete='new-password' value=''></label><button type='submit'>Save credentials</button><button type='button' data-delete-provider='printify'>Delete credential</button><span data-credential-status='printify'>checking</span></form><form data-provider='etsy'><label>Etsy API key <input type='password' name='secret' autocomplete='new-password' value=''></label><button type='submit'>Save credentials</button><button type='button' data-delete-provider='etsy'>Delete credential</button><span data-credential-status='etsy'>checking</span></form><p><small>Blank fields preserve the current secret. Values are never returned to this page.</small></p></div></article><article class='layout-panel' data-panel-id='network_access' data-layout-locked='true' aria-labelledby='access-status-title'><header class='panel-title' id='access-status-title'>Network access <span>🔒</span></header><div class='panel-content' id='access-status' aria-live='polite'><p>Access mode: <strong id='access-mode'>checking</strong></p><p>Trusted hostname: <strong id='access-host'>checking</strong></p><p>HTTPS state: <strong id='access-https'>checking</strong></p><p>Direct client/proxy type: <strong id='access-connection'>checking</strong></p><p>Access scope: <strong id='access-scope'>checking</strong></p><p id='access-warning' class='dock-badge warning' hidden></p></div></article><article class='layout-panel' data-panel-id='commerce_profiles'><header class='panel-title'>Commerce profiles <span></span></header><div class='panel-content'>Bagholder Supply Co. · UnityStitches<br><small>Sanitized destination and configured credential state only.</small></div></article><article class='layout-panel' data-panel-id='layouts_appearance'><header class='panel-title'>Layouts and appearance <span></span></header><div class='panel-content'>Saved layouts · Reset layout · Theme selection · system/Jade locks</div></article><article class='layout-panel' data-panel-id='admin_diagnostics'><header class='panel-title'>Diagnostics <span></span></header><div class='panel-content'>Sanitized application logs · failed job stages · attachment-storage health · configuration validation<br><button type='button' id='test-connections'>Test read-only connections</button></div></article></div></section>"""
    old_admin=re.search(r"<section id='admin-view' hidden>.*?</section><section id='generic-view'",page).group(0)
    page=page.replace(old_admin,admin+"<section id='generic-view'",1)
    page=page.replace("<input type='password' name='secret' autocomplete='new-password' value=''>","<input type='password' name='secret' autocomplete='new-password' value='' readonly><button type='button' data-credential-edit>Edit</button>")
    ehf_panel="""<article class='layout-panel' data-panel-id='errors_diagnostics' data-layout-locked='true'><header class='panel-title'>Errors &amp; Diagnostics <span>🔒</span></header><div class='panel-content'><div id='ehf-summary'></div><form id='ehf-filters'><label>Severity <select name='severity'><option value=''>All</option><option>warning</option><option>error</option><option>critical</option></select></label><label>Operation <input type='text' name='operation'></label><label>Stage <input type='text' name='stage'></label><label>Job <input type='text' name='job'></label><label>From <input type='date' name='date_from'></label><label>To <input type='date' name='date_to'></label><label>State <select name='resolved'><option value=''>All</option><option value='false'>Unresolved</option><option value='true'>Resolved</option></select></label><button type='submit'>Filter</button><button type='button' id='export-ehf'>Export sanitized report</button></form><div id='ehf-records' aria-live='polite'></div><aside id='ehf-detail' class='confirmation' hidden><button type='button' id='close-ehf-detail'>Close</button><h4>Sanitized error detail</h4><div id='ehf-detail-content'></div></aside><p><small>Bounded EHF records only. Raw logs, private paths, prompts, attachments, and credentials are unavailable to the browser.</small></p></div></article>"""
    page=page.replace("<article class='layout-panel' data-panel-id='admin_diagnostics'>",ehf_panel+"<article class='layout-panel' data-panel-id='admin_diagnostics'>",1)
    adult_admin=f"""<article class='layout-panel' data-panel-id='adult_mode_policy' data-layout-locked='true'><header class='panel-title'>Private chat policy <span>🔒</span></header><div class='panel-content'><form id='adult-policy' data-revision='{html_escape(private_policy['revision'],quote=True)}' data-editing='false'><label>Adult mode availability: <input type='checkbox' name='adult_mode_available' {'checked' if private_policy['adult_mode_available'] else ''} disabled> <strong id='adult-policy-state'>{'Enabled' if private_policy['adult_mode_available'] else 'Disabled'}</strong></label><p><small>This controls availability only. The Administrator cannot activate a user's Adult chat session.</small></p><button type='button' id='edit-adult-policy'>Edit</button><button type='submit' id='save-adult-policy' hidden>Save</button><button type='button' id='cancel-adult-policy' hidden>Cancel</button></form></div></article>"""
    page=page.replace("<article class='layout-panel' data-panel-id='admin_diagnostics'>",adult_admin+"<article class='layout-panel' data-panel-id='admin_diagnostics'>",1)
    chat_panel="<article class='layout-panel' data-panel-id='chat_diagnostics'><header class='panel-title'>Chat diagnostics <span></span></header><div class='panel-content'><button type='button' id='refresh-chat-diagnostics'>Refresh</button><h4>Readiness</h4><div id='chat-readiness'>Not tested</div><h4>Last generation</h4><div id='chat-generation'>Not requested</div><h4>Application shell</h4><div id='chat-parsing'>Not run</div></div></article>"
    page=page.replace("<article class='layout-panel' data-panel-id='admin_services'>",chat_panel+"<article class='layout-panel' data-panel-id='admin_services'>",1)
    profile_records={str(item.get("profile_id") or ""):item for item in profiles};profile_revision=ShellProfileSettings().revision();profile_parts=[]
    for pid,label in (("bagholder-supply","Bagholder Supply Co."),("unitystitches","UnityStitches")):
        record=profile_records.get(pid,{}) or {};config=record.get("configuration") or {};values={"display_name":record.get("display_name") or label,"printify_shop_title":config.get("printify_shop_title") or label,"printify_shop_id":config.get("printify_shop_id") or "","etsy_shop_slug":config.get("etsy_shop_slug") or "","garment_defaults":", ".join(config.get("default_garment_colors") or config.get("garment_colors") or []),"artwork_palette":", ".join(config.get("artwork_palette") or config.get("palette") or []),"brand_voice":", ".join(config.get("brand_voice") or []),"listing_guidance":config.get("listing_policy_reference") or f"{pid}-listing-v1"}
        fields="".join(f"<label>{html_escape(title)} <input name='{name}' type='text' value='{html_escape(str(values[name]),quote=True)}' readonly></label>" for name,title in (("display_name","Display name"),("printify_shop_title","Printify shop title"),("printify_shop_id","Printify shop ID"),("etsy_shop_slug","Etsy shop slug"),("garment_defaults","Garment defaults"),("artwork_palette","Artwork-palette guidance"),("brand_voice","Brand voice"),("listing_guidance","Listing guidance identifier")))
        profile_parts.append(f"<form data-profile-settings='{pid}' data-revision='{profile_revision}' data-editing='false'><h4>{label}</h4><p class='editing-state'>Read only</p>{fields}<p><small>Listing guidance defines the identifier, purpose, brand voice, title and description guidance, exactly 13 tag guidance, and prohibited-content rules. Existing bound-job destinations remain immutable.</small></p><button type='button' data-profile-edit>Edit</button><button type='submit' data-profile-save hidden>Save</button><button type='button' data-profile-cancel hidden>Cancel</button><output data-profile-preview></output></form>")
    profile_forms="<div class='panel-content' id='profile-settings'><p>Existing bound job destinations are immutable.</p>"+"".join(profile_parts)+"</div>"
    page=re.sub(r"(<article class='layout-panel' data-panel-id='commerce_profiles'><header class='panel-title'>Commerce profiles <span></span></header>)<div class='panel-content'>.*?</div>",r"\1"+profile_forms,page,count=1)
    page=page.replace("<section id='admin-view' hidden><h3>Admin</h3>", "<section id='admin-view' hidden><h3>Admin</h3><p class='muted'>Profiles · Service status · Themes · Layouts · Permissions · Diagnostics</p>", 1)
    page=page.replace("id='access-status-title'>Network access", "id='access-status-title'>Private-network access", 1)
    review_html="<section id='commerce-review' hidden><h3>Product review</h3><p>Select a completed unpublished draft or return to Product Studio.</p><button type='button' data-view='commerce.new'>Return to Product Studio</button></section>"
    if active=="commerce.review" and requested_job:
        try:
            review_service=CommerceCreationService();review=review_service.review_snapshot(requested_job);tags="".join(f"<li>{html_escape(tag)}</li>" for tag in review["tags"]);timeline=" → ".join(html_escape(str(item)) for item in review["workflow_timeline"]);dimensions=" × ".join(str(item) for item in review["dimensions"] if item is not None)
            pf=review.get("printify_package") or {};etsy=review.get("etsy_package") or {};mockups=review.get("mockups") or [];artwork_url=str(review.get("artwork_url") or "")
            local_candidates=review.get("local_candidates") or [];assets=([{"url":artwork_url,"label":"Current draft artwork","garment_color":"Transparent artwork","view":"front","source":"Current provider-bound artwork"}] if artwork_url else [])+mockups+local_candidates
            thumbs="".join(f"<button type='button' class='gallery-thumb' data-gallery-src='{html_escape(str(item.get('url') or ''),quote=True)}' data-gallery-label='{html_escape(str(item.get('label') or ''),quote=True)}'><img src='{html_escape(str(item.get('url') or ''),quote=True)}' alt='{html_escape(str(item.get('label') or 'Gallery asset'),quote=True)} thumbnail' referrerpolicy='same-origin'><span>{html_escape(str(item.get('label') or 'Asset'))} · {html_escape(str(item.get('view') or 'front'))} · {html_escape(str(item.get('source') or ''))}</span></button>" for item in assets)
            preview=(f"<div id='review-preview-stage' data-background='dark' style='padding:1rem;max-width:560px;background:#17191d'><img id='review-artwork-preview' src='{html_escape(artwork_url,quote=True)}' alt='Selected product asset' referrerpolicy='same-origin' style='display:block;max-width:100%;max-height:560px;margin:auto'></div><p id='gallery-selected-label'>Current draft artwork</p><div role='group' aria-label='Preview background'><button type='button' data-preview-background='dark'>Dark</button><button type='button' data-preview-background='light'>Light</button><button type='button' data-preview-background='transparency'>Transparency</button></div><div id='review-gallery' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.6rem;max-width:760px'>{thumbs}</div><p id='review-artwork-fallback' hidden>Artwork preview unavailable. The unpublished draft remains unchanged.</p>" if assets else "<p>Artwork preview unavailable. The unpublished draft remains unchanged.</p>")
            missing_mockup="<p>No saved mockup is available for this color.</p>" if not mockups else ""
            variant_ids=pf.get("variant_ids") or [];variants=pf.get("variants") or []
            review_identity,bound=_application_review_identity(review_service,requested_job);destination=bound.get("destination") or {};price=bound.get("price_cents")
            confirmation=_application_publication_confirmation(str(review.get("printify_product_id") or ""),str(destination.get("etsy_shop_slug") or ""))
            state_path=review_service.orchestrator._path(requested_job)
            execution_path=state_path.parent/"commerce-proposal"/"publication-execution.json" if isinstance(state_path,Path) else None
            execution=json.loads(execution_path.read_text()) if execution_path is not None and execution_path.is_file() else {}
            published=(f"<section id='final-publication-result' class='safeguard'><h4>Published</h4><p><strong>Printify product ID:</strong> {html_escape(str(review.get('printify_product_id') or ''))}<br><strong>Etsy listing:</strong> {html_escape(str(execution.get('public_listing_url') or execution.get('verified_final_state') or 'provider result recorded'))}<br><strong>Final destination:</strong> {html_escape(str(destination.get('etsy_shop_slug') or ''))}<br><strong>Publication timestamp:</strong> {html_escape(str(execution.get('completed_at') or ''))}<br><strong>Order state:</strong> not created</p></section>" if execution.get("status")=="completed" else "")
            final_review=(f"<section id='final-review-panel' class='layout-panel' data-review-identity='{review_identity}' data-revision='{int(bound.get('revision_number') or 0)}' data-destination='{html_escape(str(destination.get('etsy_shop_slug') or ''),quote=True)}'><h4>Final human approval</h4><p><strong>Brand and destination:</strong> {html_escape(str(review.get('brand_display_name') or ''))} → {html_escape(str(destination.get('etsy_shop_slug') or ''))}<br><strong>Printify shop:</strong> {html_escape(str(destination.get('printify_shop_title') or review.get('printify_shop_title') or ''))} / {html_escape(str(destination.get('printify_shop_id') or ''))}<br><strong>Etsy shop:</strong> {html_escape(str(destination.get('etsy_shop_slug') or ''))}<br><strong>Printify product ID:</strong> {html_escape(str(review.get('printify_product_id') or ''))}<br><strong>Title:</strong> {html_escape(str(bound.get('title') or ''))}<br><strong>Sale price:</strong> {('$%.2f' % (price/100)) if isinstance(price,int) else 'not recorded'}<br><strong>Colors:</strong> {html_escape(', '.join(map(str,bound.get('colors') or [])))}<br><strong>Sizes:</strong> {html_escape(', '.join(map(str,bound.get('sizes') or [])))}<br><strong>Enabled variants:</strong> {html_escape(', '.join(map(str,bound.get('enabled_variants') or [])))}<br><strong>Placement:</strong> {html_escape(str(bound.get('placement') or ''))}<br><strong>Selected artwork:</strong> {html_escape(str(bound.get('selected_artwork') or ''))}<br><strong>Mockups:</strong> {len(mockups)}<br><strong>Current publication state:</strong> {html_escape(str(review.get('publication_status') or 'not_published'))}<br><strong>No customer order will be created.</strong></p><details><summary>Exact description</summary><pre style='white-space:pre-wrap'>{html_escape(str(bound.get('description') or ''))}</pre></details><details open><summary>All 13 tags</summary><ol>{tags}</ol></details>{published}<button type='button' class='approve' id='approve-and-publish' {'disabled' if execution.get('status')=='completed' else ''}>Approve and Publish to Etsy</button><p id='publication-action-status' aria-live='polite'></p></section>")
            try:intake=MockupReviewService(review_service.orchestrator).public(requested_job)
            except JamesOSError:intake={"provider_image_count":0,"mockups":[],"approval":None,"sync_warning":"Printify mockup intake is unavailable for this review."}
            intake_cards="".join(f"<article class='mockup-intake-card' data-mockup-asset='{html_escape(str(item.get('asset_id') or ''),quote=True)}'><img src='{html_escape(str(item.get('url') or ''),quote=True)}' alt='{html_escape(str(item.get('title') or 'Printify mockup'),quote=True)}' style='width:100%;max-height:180px;object-fit:contain'><strong>{html_escape(str(item.get('title') or 'Printify mockup'))}</strong><small>{html_escape(str(item.get('dimensions') or []))} · {html_escape(str(item.get('position') or 'unknown'))}</small><label>Role <select data-mockup-role><option value='unassigned'>Unassigned</option><option value='clean_front' {'selected' if item.get('suggested_role')=='clean_front' else ''}>Clean front</option><option value='male_model' {'selected' if item.get('suggested_role')=='male_model' else ''}>Male model</option><option value='female_model' {'selected' if item.get('suggested_role')=='female_model' else ''}>Female model</option></select></label><label><input type='radio' name='mockup-primary' {'checked' if index==0 else ''}> Primary</label><button type='button' data-mockup-up>↑</button><button type='button' data-mockup-down>↓</button><button type='button' data-mockup-remove>Remove</button></article>" for index,item in enumerate(intake.get('mockups') or []))
            sync=f"<p class='confirmation'>{html_escape(str(intake.get('sync_warning')))}</p>" if intake.get('sync_warning') else ""
            approved=intake.get('approval') or {};approval_message=f"<p class='safeguard'>Mockups approved locally.<br>Etsy has not been updated.<br>Proposal: {html_escape(str(approved.get('proposal_sha256') or '')[:12])}…</p>" if approved else ""
            mockup_intake=(f"<section id='mockup-intake-review' class='layout-panel'><h4>Printify mockup intake</h4><p>Read-only import for product {html_escape(str(review.get('printify_product_id') or ''))}. Choose clean front, male model, and female model roles, set the primary image, and arrange the proposed order.</p>{sync}<div id='mockup-intake-gallery' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.65rem'>{intake_cards}</div>{approval_message}<button type='button' id='refresh-printify-mockups'>Refresh Printify mockups</button> <button type='button' id='approve-mockups-locally' {'disabled' if len(intake.get('mockups') or [])<3 else ''}>Approve mockups locally</button><p id='mockup-intake-status' aria-live='polite'></p></section>")
            try:composer=DeterministicMockupComposer(review_service.orchestrator).public(requested_job);templates=MockupTemplateRegistry().list().get("templates") or []
            except Exception:composer={"stage":"mockup_templates_selected","outputs":[]};templates=[]
            options="".join(f"<option value='{html_escape(str(t['template_id']+'@'+t['version']),quote=True)}' data-category='{html_escape(str(t['model_category']),quote=True)}'>{html_escape(str(t.get('display_name') or t['template_id']))} v{html_escape(str(t['version']))} · {html_escape(str(t['model_category']))} · {html_escape(str(t.get('garment_color') or ''))}</option>" for t in templates if t.get('production_allowed') is True)
            def composer_card(x):return f"<article data-composed-asset='{html_escape(str(x.get('asset_id') or ''),quote=True)}' style='min-width:0'><img src='{html_escape(str(x.get('url') or ''),quote=True)}' alt='{html_escape(str(x.get('role') or 'mockup'),quote=True)}' style='width:100%;height:340px;max-height:340px;object-fit:contain'><strong>{html_escape(str(x.get('role') or ''))}</strong><label><input type='radio' name='composed-primary'> Primary</label><button type='button' data-composed-up>Move left</button><button type='button' data-composed-down>Move right</button><button type='button' data-composed-regenerate>Replace / regenerate</button><button type='button' data-composed-remove>Remove</button><details><summary>Details</summary><small>Template {html_escape(str(x.get('template_id') or ''))} v{html_escape(str(x.get('template_version') or ''))}<br>Output hash {html_escape(str(x.get('output_sha256') or ''))}<br>Mask hash {html_escape(str(x.get('mask_sha256') or ''))}<br>Dimensions {html_escape(str(x.get('dimensions') or ''))}<br>Polygon {html_escape(str(x.get('print_area') or ''))}<br>Method {html_escape(str(x.get('algorithm') or ''))}<br>Provenance {html_escape(str(x.get('provenance') or ''))}</small></details></article>"
            production_outputs=[x for x in composer.get('outputs') or [] if x.get('production_allowed') is True];placeholder_outputs=[x for x in composer.get('outputs') or [] if x.get('production_allowed') is not True];composed_cards="".join(composer_card(x) for x in production_outputs);developer_cards="<ul>"+"".join(f"<li>{html_escape(str(t.get('display_name') or t.get('template_id')))} — not production eligible</li>" for t in templates if t.get('template_kind')=='placeholder')+"</ul>"+"".join(composer_card(x) for x in placeholder_outputs)
            composer_approval=composer.get("approval") or {};composer_message=f"<p class='safeguard'>Mockups approved locally.<br>Etsy and Printify have not been updated.</p>" if composer.get('stage')=='mockups_approved' else ""
            no_production="<p class='confirmation'><strong>No production-quality model templates are installed.</strong><br>The deterministic compositor is working, but realistic blank-shirt templates must be imported or generated before Etsy use.</p>" if not any(t.get('production_allowed') for t in templates) else ""
            composer_panel=(f"<section id='deterministic-mockup-composer' class='layout-panel' style='max-width:100%;overflow:hidden'><h4>Production mockup review</h4><p>Exact approved artwork is composited locally. No diffusion model or external provider is used.</p>{no_production}<div class='field-grid'>"+"".join(f"<label>{label}<select data-composer-role='{role}'><option value=''>Select production template</option>{options}</select><button type='button' data-compose-role='{role}'>Compose</button></label>" for role,label in (("clean_product","Clean product"),("male_model","Male model"),("female_model","Female model")))+f"</div><div id='composed-mockup-gallery' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:.75rem;max-width:100%;overflow:hidden'>{composed_cards}</div>{composer_message}<button type='button' id='approve-composed-mockups' {'disabled' if len(production_outputs)<3 else ''}>Approve mockups locally</button><p id='composer-status' aria-live='polite'></p><details><summary>Developer/Test Templates</summary><p>These templates verify the compositor but are not eligible for marketplace use.</p><div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:.65rem'>{developer_cards}</div></details><details><summary>Add Blank-Shirt Template</summary><p>Use the protected local template-ingestion API to add a base image, shirt mask, role, polygon, provenance, license, and explicitly confirmed production eligibility.</p></details></section>")
            review_html=(f"<section id='commerce-review'><h3>Product package review</h3><section><h4>Status</h4><p class='safeguard'><strong>Ready for review</strong><br>UNPUBLISHED PRINTIFY DRAFT · NO ETSY LISTING · NO ORDER CREATED</p><p><strong>Destination:</strong> {html_escape(str(review.get('brand_display_name') or ''))}<br><strong>Printify shop:</strong> {html_escape(str(review.get('printify_shop_title') or ''))}<br><strong>Printify product ID:</strong> <code id='review-draft-id'>{html_escape(str(review.get('printify_product_id') or ''))}</code><br><strong>Provider contacted:</strong> {'yes' if review.get('provider_contacted') else 'no'}<br><strong>Publication:</strong> no<br><strong>Etsy listing:</strong> no<br><strong>Order:</strong> no</p></section>"
                f"<section><h4>Visual assets ({len(assets)})</h4>{preview}{missing_mockup}<p><strong>Selected candidate:</strong> {html_escape(str(review.get('selected_candidate_id') or ''))}<br><strong>Generation method:</strong> {html_escape(str(review.get('generation_method') or ''))}<br><strong>Dimensions:</strong> {dimensions}<br><strong>Transparency:</strong> yes<br><strong>Artwork palette:</strong> {html_escape(', '.join(map(str,review.get('artwork_palette') or [])))}<br><strong>Garment colors:</strong> {html_escape(', '.join(map(str,review.get('garment_colors') or [])))}</p></section>"
                f"<section id='sent-to-printify'><h4>Sent to Printify</h4><p>{'Exact persisted prepared request' if pf.get('verified_from_prepared_request') else 'Persisted draft metadata; historical jobs may predate prepared-request recording'}</p><p><strong>Product title:</strong> {html_escape(str(pf.get('title') or review.get('listing_title') or ''))}<br><strong>Blueprint:</strong> {html_escape(str(pf.get('blueprint_name') or ''))} · ID {html_escape(str(pf.get('blueprint_id') or ''))}<br><strong>Print provider:</strong> {html_escape(str(pf.get('print_provider_name') or ''))} · ID {html_escape(str(pf.get('print_provider_id') or ''))}<br><strong>Selected garment colors:</strong> {html_escape(', '.join(map(str,pf.get('garment_colors') or [])))}<br><strong>Selected sizes:</strong> {html_escape(', '.join(map(str,pf.get('sizes') or [])))}<br><strong>Print placement:</strong> {html_escape(str(pf.get('print_placement') or 'front'))}<br><strong>Uploaded image ID:</strong> {html_escape(str(pf.get('uploaded_image_id') or ''))}<br><strong>Unpublished state:</strong> yes</p><details open><summary>Product description sent to Printify</summary><pre id='printify-description' style='white-space:pre-wrap'>{html_escape(str(pf.get('description') or review.get('description') or ''))}</pre><button type='button' data-copy-target='printify-description'>Copy description</button></details><details><summary>Enabled variants ({len(variant_ids)})</summary><p>{html_escape(', '.join(map(str,variant_ids)))}</p><pre>{html_escape(json.dumps(variants,indent=2))}</pre></details></section>"
                f"<section id='prepared-for-etsy'><h4>Prepared for Etsy</h4><p><strong>Prepared locally — not published to Etsy</strong></p><p><strong>Listing title:</strong> {html_escape(str(etsy.get('title') or review.get('listing_title') or ''))}<br><strong>Store profile:</strong> {html_escape(str(etsy.get('profile_id') or ''))}<br><strong>Listing guidance:</strong> {html_escape(str(etsy.get('listing_guidance') or ''))}<br><strong>Exact phrase:</strong> {html_escape(str(etsy.get('exact_phrase') or ''))}</p><details open><summary>Etsy-ready description</summary><pre id='etsy-description' style='white-space:pre-wrap'>{html_escape(str(etsy.get('description') or review.get('description') or ''))}</pre></details><p><strong>Etsy tags ({len(review['tags'])}):</strong></p><ol id='review-tags'>{tags}</ol></section>"
                f"<section><h4>Workflow</h4><p><strong>Timeline:</strong> {timeline}<br><strong>Provider-write state:</strong> completed<br><strong>Mockup count:</strong> {len(mockups)}<br><strong>Review-ready state:</strong> yes<br><strong>Publication state:</strong> not published<br><strong>Order state:</strong> not created</p></section>"
                f"{mockup_intake}{composer_panel}{final_review}<div class='actions'><button type='button' id='regenerate-review-artwork'>Regenerate local artwork</button><button type='button' disabled title='{html_escape(str(review.get('update_existing_draft_reason') or ''),quote=True)}'>Update existing unpublished draft</button><button type='button' data-view='commerce.new'>Return to Product Studio</button></div></section>")
        except Exception as exc:
            try:handle_error(exc,operation="commerce_review_render",context={"job_id":requested_job if re.fullmatch(r"product-[A-Za-z0-9._-]{1,120}",requested_job) else None},state={"provider_contacted":False,"publish_status":"not_published","order_status":"not_created"})
            except Exception:pass
            review_html="<section id='commerce-review'><h3>Product review unavailable</h3><p>The selected review could not be loaded safely.</p><button type='button' data-view='commerce.new'>Return to Product Studio</button></section>"
    page=page.replace("<section id='generic-view' hidden><h3 id='generic-title'></h3><p id='generic-copy'></p></section>",dashboard+review_html+"<section id='generic-view' hidden><h3 id='generic-title'></h3><p id='generic-copy'></p></section>")
    diagnostics="""<section id='product-failure' class='layout-panel' data-layout-locked='true' hidden><header class='panel-title'>Product Studio diagnostics <span>🔒</span></header><div class='panel-content'><p id='failure-stage'>Last completed stage: none</p><p id='failure-draft'>Printify draft exists: no</p><p id='failure-published'>Anything published: no</p><p id='failure-order'>Order exists: no</p><div id='artwork-diagnostics' aria-live='polite'>Artwork diagnostics are available when a job fails.</div><ul><li>Check that the image-generation service is ready.</li><li>Inspect generated candidate count and eligibility rejection reasons.</li><li>Adjust the artwork brief and retry local generation.</li></ul><button type='button' id='retry-local-artwork'>Retry local artwork generation</button> <button type='button' data-view='commerce.new'>Edit product brief</button> <button type='button' data-view='commerce.new'>Return to Product Studio</button> <button type='button' id='view-sanitized-diagnostics'>View sanitized diagnostics</button></div></section>"""
    page=page.replace("<section id='generic-view' hidden>",diagnostics+"<section id='generic-view' hidden>",1)
    needs="""<article class='layout-panel' data-panel-id='needs_attention'><header class='panel-title'>Needs attention <span></span></header><div class='panel-content' id='dashboard-attention'>No failed jobs, unresolved errors, pending approvals, or degraded services.</div></article>"""
    page=page.replace("<article class='layout-panel' data-panel-id='work_in_progress'>",needs+"<article class='layout-panel' data-panel-id='work_in_progress'>",1)
    page=page.replace("<header class='panel-title'>System overview", "<header class='panel-title'>System status",1)
    page=page.replace("<button type='button' data-view='jobs.list'>View failed jobs</button>","<button type='button' data-view='admin.home' id='view-errors'>View Errors &amp; Diagnostics</button>")
    page=page.replace("Start a new conversation","Clear chat")
    page=page.replace("<div class='activity-actions'><strong>Activity</strong></div><div class='activity' id='activity'></div>","")
    page=page.replace("function log(text){activity.push(text);activity=activity.slice(-50);q('activity').replaceChildren(...activity.map(x=>{let p=document.createElement('div');p.textContent=x;return p}))}","function log(text){activity.push(text);activity=activity.slice(-50)}")
    page=page.replace("q('activity').replaceChildren();","")
    page=page.replace("bind('prepare-generation','click',()=>confirm({action:'start_generation',message:'Confirm destination '+(selected()?.dataset.etsy||'')+' before creating an unpublished Printify draft.'}));","bind('prepare-generation','click',()=>{if(q('commerce-form').reportValidity()){sessionStorage.setItem('jamesos-commerce-form',JSON.stringify({profile:profileSelect.value,form:formState()}));q('commerce-form').requestSubmit()}});")
    page=page.replace("let conversation=localStorage.getItem('jamesos-conversation-id')||crypto.randomUUID(),activeView=initialView,selectedJob=''", "let conversation=localStorage.getItem('jamesos-conversation-id')||crypto.randomUUID(),activeView=initialView,selectedJob=new URLSearchParams(location.search).get('job_id')||''")
    page=page.replace("q('agency-view').hidden=view!=='agency.home';q('admin-view').hidden=view!=='admin.home';if(view==='agency.home'||view==='admin.home'){q('commerce-new').hidden=true;q('generic-view').hidden=true}","q('agency-view').hidden=view!=='agency.home';q('admin-view').hidden=view!=='admin.home';q('dashboard-view').hidden=view!=='dashboard';if(view==='agency.home'||view==='admin.home'||view==='dashboard'){q('commerce-new').hidden=true;q('generic-view').hidden=true}")
    page=page.replace("q('agency-view').hidden=view!=='agency.home'","q('agency-view').hidden=!view.startsWith('agency.')").replace("view==='agency.home'||view==='admin.home'||view==='dashboard'","view.startsWith('agency.')||view==='admin.home'||view==='dashboard'")
    page=page.replace("if(status.failed){navigate('diagnostics');q('generic-copy').textContent=status.failure_message_safe||'Product preparation did not complete.';return}","if(status.failed){sessionStorage.setItem('jamesos-safe-job-failure',status.failure_message_safe||'Product preparation did not complete.');location.replace('/app?view=commerce.diagnostics&job_id='+encodeURIComponent(selectedJob));return}")
    page=page.replace("navigate(activeView);let healthState", "navigate(activeView);if(selectedJob)watchJob();let healthState")
    page=page.replace("navigate(activeView);if(selectedJob)watchJob();let healthState", "navigate(activeView);try{const saved=JSON.parse(sessionStorage.getItem('jamesos-commerce-form')||'null');if(saved&&saved.form){if(saved.profile&&profileUi[saved.profile])profileSelect.value=saved.profile;applyingProfile=true;Object.entries(saved.form).forEach(([key,value])=>{if(fields.includes(key)&&typeof value==='string')q(key).value=value});applyingProfile=false;identity()}}catch(e){}if(selectedJob)watchJob();let healthState")
    page=page.replace("q('dashboard-view').hidden=view!=='dashboard';if(view===", "q('dashboard-view').hidden=view!=='dashboard';if(q('product-failure')&&view!=='commerce.diagnostics')q('product-failure').hidden=true;if(view===")
    page=page.replace("q('dashboard-view').hidden=view!=='dashboard';if(q('product-failure')", "q('dashboard-view').hidden=view!=='dashboard';if(q('commerce-review'))q('commerce-review').hidden=view!=='commerce.review';if(view==='commerce.review')q('generic-view').hidden=true;if(q('product-failure')")
    extra="""function diagnosticLines(values){const node=document.createDocumentFragment();for(const [label,value] of values){const p=document.createElement('p');p.textContent=label+': '+String(value??'none');node.append(p)}return node}async function loadChatDiagnostics(){try{const r=await fetch('/app/chat-diagnostics',{cache:'no-store'}),v=await r.json();if(!r.ok)throw new Error();q('chat-readiness').replaceChildren(diagnosticLines([['Ollama',v.readiness.reachable===true?'reachable':v.readiness.reachable===false?'unreachable':'not tested'],['Configured model',v.readiness.model||'configured locally'],['Model installed',v.readiness.model_installed??'not tested'],['Readiness timestamp',v.readiness.timestamp]]));q('chat-generation').replaceChildren(diagnosticLines([['Timestamp',v.generation.timestamp],['Endpoint mode',v.generation.endpoint_mode],['HTTP status',v.generation.http_status],['Schema supplied',v.generation.schema_supplied?'yes':'no'],['Response field',v.generation.shape],['Returned text length',v.generation.text_length]]));q('chat-parsing').replaceChildren(diagnosticLines([['Active view ID',v.application_shell.active_view_id],['Structured parse',v.application_shell.structured_parse],['Fallback used',v.application_shell.fallback_used?'yes':'no'],['Final message length',v.application_shell.final_message_length],['Command count',v.application_shell.commands_count],['Failure stage',v.application_shell.failure_stage]]))}catch(e){q('chat-parsing').textContent='Sanitized chat diagnostics are unavailable.'}}async function loadDashboard(){try{const r=await fetch('/app/dashboard-status',{cache:'no-store'}),v=await r.json();q('dashboard-summary').textContent=v.summary.label;q('dashboard-systems').replaceChildren(...v.systems.map(x=>{const n=document.createElement('li');n.textContent=x.label+': '+x.status;return n}));q('dashboard-work').textContent='Active jobs: '+v.work.active.length+' · Failed jobs: '+v.work.failed.length+' · Ready for review: '+v.work.ready.length+' · Pending confirmations: '+v.work.pending_confirmations+' · Agency runs: '+v.work.agency_runs;q('dashboard-results').textContent=v.recent_results.length?v.recent_results.map(x=>x.kind+' — '+x.status+' — '+x.publication_state+' — '+x.destination).join(' | '):'No recent results.'}catch(e){q('dashboard-summary').textContent='Dashboard status is temporarily unavailable; navigation remains available.'}}async function loadCredentials(){try{const r=await fetch('/app/admin/credentials',{cache:'no-store'}),v=await r.json();v.providers.forEach(x=>{const n=document.querySelector('[data-credential-status="'+x.provider+'"]');if(n)n.textContent=x.configured?'configured · '+(x.masked||'masked')+' · updated '+(x.last_updated||'unknown'):'not configured'})}catch(e){}}document.querySelectorAll('#credential-controls form').forEach(form=>{const input=form.elements.secret,edit=form.querySelector('[data-credential-edit]'),save=form.querySelector('button[type=submit]');save.hidden=true;edit.onclick=()=>{input.readOnly=false;edit.hidden=true;save.hidden=false};form.addEventListener('submit',async event=>{event.preventDefault();if(input.readOnly)return;const secret=input.value,provider=form.dataset.provider;await fetch('/app/admin/credentials/'+provider,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,secret})});input.value='';input.readOnly=true;edit.hidden=false;save.hidden=true;loadCredentials()})});document.querySelectorAll('[data-delete-provider]').forEach(button=>button.onclick=async()=>{if(!window.confirm('Delete this credential?'))return;await fetch('/app/admin/credentials/'+button.dataset.deleteProvider,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,confirmed:true})});loadCredentials()});bind('refresh-chat-diagnostics','click',loadChatDiagnostics);bind('new-conversation','click',()=>q('reset').click());bind('test-connections','click',()=>{q('chat-state').textContent='Read-only checks are not run automatically.'});loadDashboard();loadCredentials();if(activeView==='admin.home')loadChatDiagnostics();"""
    ehf_js="""function ehfQuery(){return new URLSearchParams(new FormData(q('ehf-filters'))).toString()}function ehfText(label,value){const p=document.createElement('p');p.textContent=label+': '+String(value??'');return p}async function loadEHF(){try{const r=await fetch('/app/admin/errors?'+ehfQuery(),{cache:'no-store'}),v=await r.json(),s=v.summary;q('ehf-summary').textContent='Unresolved errors: '+s.unresolved_errors+' · Warnings: '+s.warnings+' · Critical failures: '+s.critical_failures+' · Failed commerce jobs: '+s.failed_commerce_jobs+' · Recent service failures: '+s.recent_service_failures+' · Last 24 hours: '+s.last_24_hours;q('ehf-records').replaceChildren(...v.records.map(item=>{const row=document.createElement('article'),summary=document.createElement('p'),detail=document.createElement('button'),copy=document.createElement('button');summary.textContent=item.timestamp+' · '+item.severity+' · '+item.code+' · '+item.operation+' / '+item.stage+' · '+item.message+' · '+(item.resolved?'resolved':'unresolved');detail.type='button';detail.textContent='Open sanitized diagnostics';detail.onclick=()=>openEHF(item.error_id);copy.type='button';copy.textContent='Copy error ID';copy.onclick=()=>navigator.clipboard?.writeText(item.error_id);row.append(summary,copy,detail);if(item.job_id){const job=document.createElement('button');job.type='button';job.textContent='Open associated job';job.onclick=()=>{selectedJob=item.job_id;navigate('jobs.detail')};row.append(job)}return row}))}catch(e){q('ehf-records').textContent='Sanitized EHF records are unavailable.'}}async function openEHF(id){const r=await fetch('/app/admin/errors/'+encodeURIComponent(id),{cache:'no-store'});if(!r.ok)return;const v=await r.json(),content=q('ehf-detail-content');content.replaceChildren(ehfText('Error ID',v.error_id),ehfText('Safe summary',v.message),ehfText('Stage',v.stage),ehfText('Job',v.job_id||'none'),ehfText('Run',v.run_id||'none'),ehfText('Retry guidance',v.retry_guidance),ehfText('Provider contacted',v.provider_contacted),ehfText('Draft exists',v.draft_exists),ehfText('Publication state',v.publication_state),ehfText('Order state',v.order_state));for(const [label,action] of [['Acknowledge','acknowledge'],['Mark resolved','resolve']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=async()=>{await fetch('/app/admin/errors/'+encodeURIComponent(id)+'/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf})});await loadEHF();await openEHF(id)};content.append(b)}q('ehf-detail').hidden=false}bind('ehf-filters','submit',event=>{event.preventDefault();loadEHF()});bind('close-ehf-detail','click',()=>q('ehf-detail').hidden=true);bind('export-ehf','click',async()=>{const r=await fetch('/app/admin/errors/export?'+ehfQuery(),{cache:'no-store'});if(r.ok){const blob=new Blob([JSON.stringify(await r.json(),null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='jamesos-ehf-sanitized.json';a.click();URL.revokeObjectURL(a.href)}});"""
    extra=ehf_js+extra.replace("loadDashboard();loadCredentials();","loadDashboard();loadCredentials();loadEHF();")
    profile_js="""document.querySelectorAll('[data-profile-settings]').forEach(form=>{const inputs=[...form.querySelectorAll('input')],edit=form.querySelector('[data-profile-edit]'),save=form.querySelector('[data-profile-save]'),cancel=form.querySelector('[data-profile-cancel]'),state=form.querySelector('.editing-state'),preview=form.querySelector('[data-profile-preview]');let before={};const lock=()=>{inputs.forEach(x=>x.readOnly=true);form.dataset.editing='false';edit.hidden=false;save.hidden=true;cancel.hidden=true;state.textContent='Read only';preview.textContent=''};edit.onclick=()=>{before=Object.fromEntries(inputs.map(x=>[x.name,x.value]));inputs.forEach(x=>x.readOnly=false);form.dataset.editing='true';edit.hidden=true;save.hidden=false;cancel.hidden=false;state.textContent='Editing'};cancel.onclick=()=>{inputs.forEach(x=>x.value=before[x.name]??x.value);lock()};inputs.forEach(input=>input.addEventListener('input',()=>{if(form.dataset.editing==='true'){const changed=inputs.filter(x=>x.value!==(before[x.name]??'')).map(x=>x.name);preview.textContent=changed.length?'Pending changes: '+changed.join(', '):'No changes'}}));form.addEventListener('submit',async event=>{event.preventDefault();if(form.dataset.editing!=='true')return;const values=Object.fromEntries([...new FormData(form)].filter(([,value])=>String(value).trim()));values.revision=form.dataset.revision;values.csrf_token=csrf;const response=await fetch('/app/admin/commerce-profiles/'+form.dataset.profileSettings,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)}),data=await response.json();if(response.ok){form.dataset.revision=data.revision;inputs.forEach(x=>before[x.name]=x.value);lock()}q('chat-state').textContent=response.ok?'Profile configuration saved for future work. Existing jobs were unchanged.':'Profile configuration was not saved.'});lock()});"""
    extra=profile_js+extra
    extra="""bind('retry-local-artwork','click',async()=>{if(!selectedJob)return;const response=await fetch('/commerce/jobs/'+encodeURIComponent(selectedJob)+'/retry-local-artwork',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf})});q('chat-state').textContent=response.ok?'Local artwork retry completed without contacting a commerce provider.':'Local artwork retry did not complete.';if(response.ok)watchJob()});bind('regenerate-review-artwork','click',async()=>{if(!selectedJob)return;const response=await fetch('/commerce/jobs/'+encodeURIComponent(selectedJob)+'/regenerate-local-artwork',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf})});q('chat-state').textContent=response.ok?'New local candidates are ready and were not sent to Printify.':'Local regeneration did not complete.';if(response.ok)location.reload()});"""+extra
    agency_js=f"""let agencyRevision={int(agency_snapshot['revision'])};function openAgencySection(name){{document.querySelectorAll('[data-agency-section]').forEach(node=>node.hidden=node.dataset.agencySection!==name);q('agency-agent-detail').hidden=true}}document.querySelectorAll('[data-agency-tab]').forEach(button=>button.onclick=()=>openAgencySection(button.dataset.agencyTab));document.querySelectorAll('[data-agent-detail]').forEach(button=>button.onclick=async()=>{{const response=await fetch('/app/agency/agents/'+encodeURIComponent(button.dataset.agentDetail),{{cache:'no-store'}});if(!response.ok)return;const value=await response.json(),content=q('agency-agent-detail-content');content.replaceChildren(...[['Name',value.name],['Role',value.role],['State',value.installation_state+' · '+value.enabled_state+' · '+value.runtime_state],['Version',value.installed_version],['Capabilities',(value.capabilities||[]).join(', ')],['Permissions',(value.permissions||[]).join(', ')],['Workspace',value.workspace],['Recent runs',(value.recent_runs||[]).length],['Pending approvals',(value.pending_approvals||[]).length]].map(([label,text])=>{{const p=document.createElement('p');p.textContent=label+': '+text;return p}}));document.querySelectorAll('[data-agency-section]').forEach(node=>node.hidden=true);q('agency-agent-detail').hidden=false;history.replaceState(null,'','/app?view=agency.agent&agent='+encodeURIComponent(value.agent_id))}});document.querySelectorAll('[data-agent-action]').forEach(button=>button.onclick=async()=>{{const path='/app/agency/agents/'+encodeURIComponent(button.dataset.agentId)+'/'+button.dataset.agentAction,preview=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{csrf_token:csrf,revision:agencyRevision,confirmed:false}})}}),value=await preview.json();if(!preview.ok)return;const message=button.dataset.agentAction==='remove'?'Remove this agent registration? Retained: '+(value.retained||[]).join(', '):'Disable this optional agent? Shared jobs and data are retained.';if(!window.confirm(message))return;const response=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{csrf_token:csrf,revision:agencyRevision,confirmed:true}})}}),result=await response.json();if(response.ok){{agencyRevision=result.revision;if(button.dataset.agentAction==='remove')button.closest('[data-agent-card]').remove();else{{const strong=button.closest('[data-agent-card]').querySelector('strong');strong.textContent=strong.textContent.replace('Enabled','Disabled')}}}}}});if(activeView==='agency.home')openAgencySection('my-agents');if(activeView==='agency.book-scout')openAgencySection('book-scout');function scoutText(label,value){{const p=document.createElement('p');p.textContent=label+': '+String(value??'');return p}}async function scoutHistory(){{const r=await fetch('/app/agency/book-scout/runs',{{cache:'no-store'}}),v=await r.json();q('book-scout-history').textContent=v.runs.length?v.runs.map(x=>x.run_id+' · '+x.status+' · '+x.candidate_count+' candidates').join(' | '):'No research runs yet.'}}function renderScout(value){{const root=q('book-scout-results');root.replaceChildren(...value.top_candidates.map((item,index)=>{{const card=document.createElement('article');card.className='agent-card';card.append(scoutText('Rank',index+1),scoutText('Concept',item.concept),scoutText('Total score',item.total_score),scoutText('Confidence',item.confidence),scoutText('Score breakdown',Object.entries(item.score_breakdown).map(([k,v])=>k+': '+v).join(' · ')),scoutText('Differentiation',item.differentiation_recommendation),scoutText('Risks',(item.risks||[]).join(', ')||'none'),scoutText('Missing evidence',(item.missing_evidence||[]).join(', ')||'none'),scoutText('Evidence',(item.evidence_references||[]).join(', ')||'unavailable'),scoutText('Research timestamp',item.research_timestamp));for(const [label,action] of [['Approve','approve'],['Reject','reject'],['Save for Later','save_for_later']]){{const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=async()=>{{const path='/app/agency/book-scout/runs/'+encodeURIComponent(value.run_id)+'/candidates/'+encodeURIComponent(item.candidate_id)+'/decision',body={{csrf_token:csrf,action,confirmed:false}},preview=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});if(!preview.ok||!window.confirm(label+' this candidate? This changes local decision state only.'))return;body.confirmed=true;const response=await fetch(path,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});q('book-scout-status').textContent=response.ok?label+' recorded locally. No book was generated or published.':'Decision was not saved.'}};card.append(button)}}return card}}))}}q('book-scout-form').onsubmit=async event=>{{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));data.candidate_count=Number(data.candidate_count);data.result_count=Number(data.result_count);data.csrf_token=csrf;q('book-scout-status').textContent='Running deterministic local research…';const response=await fetch('/app/agency/book-scout/runs',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}}),value=await response.json();if(response.ok){{renderScout(value);q('book-scout-status').textContent=value.status+' · '+value.candidate_count+' candidates · no publication or marketplace write';scoutHistory()}}else q('book-scout-status').textContent='Research request was not accepted.'}};scoutHistory();"""
    agency_js=agency_js.replace("function renderScout(value){", "function renderScout(value){const s=value.research_summary||{},summary=q('book-scout-live-summary');summary.replaceChildren(scoutText('Research label',value.research_label),scoutText('Sources attempted',(s.sources_attempted||[]).join(', ')||'none'),scoutText('Sources completed',(s.sources_completed||[]).join(', ')||'none'),scoutText('Sources blocked',(s.sources_blocked||[]).join(', ')||'none'),scoutText('Evidence collected',s.evidence_collected??0),scoutText('Cache age',s.cache_age_seconds==null?'not cached':s.cache_age_seconds+' seconds'),scoutText('Missing metrics',(s.missing_metrics||[]).join(', ')||'none'),scoutText('Overall confidence',s.overall_confidence??0),scoutText('Collection warnings',(s.collection_warnings||[]).join(' · ')||'none'));" )
    agency_js=agency_js.replace("async function scoutHistory(){", "let currentScoutRun='';function renderScoutDecision(card,decision){card.querySelector('[data-scout-decision]')?.remove();if(!decision)return;const box=document.createElement('section'),badge=document.createElement('strong'),labels={approve:'Approved',reject:'Rejected',save_for_later:'Saved for Later'};box.dataset.scoutDecision=decision.action;box.className='scout-decision';badge.className='scout-decision-badge';badge.textContent=labels[decision.action]||'Decision recorded';box.append(badge,scoutText('Recorded',decision.timestamp));if(decision.reason)box.append(scoutText('Reason',decision.reason));if(decision.action==='approve'){const status=document.createElement('p'),next=document.createElement('p'),button=document.createElement('button'),help=document.createElement('small');status.textContent='Approved for production planning';next.textContent='Next step: Coloring Book Producer is not installed yet. No book has been generated.';button.type='button';button.disabled=true;button.textContent='Create Book Project';help.textContent='Available after the Coloring Book Producer agent is installed.';box.append(status,next,button,help)}card.prepend(box)}async function loadScoutRun(runId){const r=await fetch('/app/agency/book-scout/runs/'+encodeURIComponent(runId),{cache:'no-store'});if(!r.ok)return;const value=await r.json();currentScoutRun=value.run_id;renderScout(value);q('book-scout-status').textContent='Loaded saved research and candidate decisions. No book was generated or published.'}async function scoutHistory(){")
    agency_js=agency_js.replace("q('book-scout-history').textContent=v.runs.length?v.runs.map(x=>x.run_id+' · '+x.status+' · '+x.candidate_count+' candidates').join(' | '):'No research runs yet.'", "const history=q('book-scout-history');history.replaceChildren(...v.runs.map(x=>{const button=document.createElement('button');button.type='button';button.textContent=x.run_id+' · '+x.status+' · '+x.candidate_count+' candidates';button.onclick=()=>loadScoutRun(x.run_id);return button}));if(!v.runs.length)history.textContent='No research runs yet.';else if(!currentScoutRun)await loadScoutRun(v.runs[0].run_id)")
    agency_js=agency_js.replace("card.className='agent-card';card.append(", "card.className='agent-card';card.dataset.candidateId=item.candidate_id;card.append(")
    agency_js=agency_js.replace("scoutText('Research timestamp',item.research_timestamp));for(const [label,action]", "scoutText('Research timestamp',item.research_timestamp));renderScoutDecision(card,item.decision||(value.decisions||{})[item.candidate_id]);for(const [label,action]")
    agency_js=agency_js.replace("const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});q('book-scout-status').textContent=response.ok?label+' recorded locally. No book was generated or published.':'Decision was not saved.'", "const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),record=await response.json();if(response.ok){item.decision=record;value.decisions=value.decisions||{};value.decisions[item.candidate_id]=record;renderScoutDecision(card,record)}q('book-scout-status').textContent=response.ok?label+' recorded locally. No book was generated or published.':'Decision was not saved.'")
    page=page.replace("</style>",".scout-decision{border:2px solid var(--accent);border-radius:.55rem;padding:.65rem;margin-bottom:.7rem;background:#211b38}.scout-decision-badge{display:inline-block;padding:.25rem .55rem;border-radius:1rem;background:var(--accent);color:white}.scout-decision small{display:block;margin-top:.35rem}</style>",1)
    agency_js=agency_js.replace("Running deterministic local research…", "Running selected read-only research mode…")
    agency_js="const initialProducerProject="+json.dumps(requested_project)+";"+agency_js
    agency_js=agency_js.replace("else renderProducerProject(v.projects.find(p=>!p.duplicate_of)?.project_id||v.projects[0].project_id)","else renderProducerProject(initialProducerProject||v.projects.find(p=>!p.duplicate_of)?.project_id||v.projects[0].project_id)")
    producer_installed=any(x["agent_id"]=="jamesos.coloring-book-producer" and x["enabled_state"]=="enabled" for x in agency_snapshot["agents"])
    agency_js=agency_js.replace("button.type='button';button.disabled=true;button.textContent='Create Book Project';help.textContent='Available after the Coloring Book Producer agent is installed.'", "button.type='button';button.disabled="+str(not producer_installed).lower()+";button.textContent='Create Book Project';help.textContent="+("'Creates a local planning project after an exact confirmation.'" if producer_installed else "'Available after the Coloring Book Producer agent is installed.'")+";button.onclick=async()=>{const route='/app/agency/book-scout/runs/'+encodeURIComponent(currentScoutRun)+'/candidates/'+encodeURIComponent(card.dataset.candidateId)+'/create-project',body={csrf_token:csrf,confirmed:false},preview=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),value=await preview.json();if(!preview.ok){q('book-scout-status').textContent=value.detail||'Install Coloring Book Producer first.';return}if(!window.confirm(value.confirmation))return;body.confirmed=true;const response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),created=await response.json();if(response.ok){q('book-scout-status').textContent='Local project created. No images, PDF, upload, publication, purchase, or order occurred.';navigate('agency.coloring-book-producer');loadColoringBookProjects()}else q('book-scout-status').textContent=created.detail||'Project was not created.'}")
    agency_js += "function producerField(label,name,value,type='text'){const l=document.createElement('label'),i=document.createElement('input');l.textContent=label+' ';i.name=name;i.type=type;i.value=String(value??'');l.append(i);return l}async function renderProducerProject(id){const response=await fetch('/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id),{cache:'no-store'}),v=await response.json(),out=q('coloring-book-project');if(!response.ok)return;out.replaceChildren();const section=title=>{const n=document.createElement('section'),h=document.createElement('h5');h.textContent=title;n.append(h);out.append(n);return n},overview=section('Overview');overview.append(scoutText('Project ID',v.project.project_id),scoutText('Status',v.project.status),scoutText('Created',v.project.created_at),scoutText('Revision',v.project.revision),scoutText('Scout run',v.source.scout_run_id),scoutText('Candidate',v.source.candidate_id),scoutText('Concept',v.source.concept),scoutText('Approval timestamp',v.source.approval_timestamp),scoutText('Source identity',v.project.source_identity),scoutText('Approval state',v.book_brief_approval.state),scoutText('Approval stale',v.book_brief_approval.stale?'yes':'no'));const brief=section('Book Brief'),form=document.createElement('form');form.append(producerField('Working title','working_title',v.book_brief.working_title),producerField('Subtitle','subtitle',v.book_brief.subtitle),producerField('Target audience','target_audience',v.book_brief.target_audience),producerField('Target age range','target_age_range',v.book_brief.target_age_range),producerField('Series name','series_name',v.book_brief.series_name),producerField('Notes','notes',v.book_brief.notes));const spec=section('Production Specification');spec.append(producerField('Trim width','trim_width',v.production_spec.trim_width,'number'),producerField('Trim height','trim_height',v.production_spec.trim_height,'number'),producerField('Coloring pages','coloring_page_count',v.production_spec.coloring_page_count,'number'),producerField('Visual style','visual_style',v.production_spec.visual_style));const save=document.createElement('button');save.type='submit';save.textContent='Save local changes';form.append(save);brief.append(form);form.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form)),specInputs=Object.fromEntries([...spec.querySelectorAll('input')].map(i=>[i.name,i.type==='number'?Number(i.value):i.value]));const r=await fetch('/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id)+'/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,book_brief:data,production_spec:specInputs})});q('coloring-book-status').textContent=r.ok?'Local project changes saved. Prior approval is stale if one existed.':'Changes were not saved.';if(r.ok)renderProducerProject(id)};section('Page Plan').append(scoutText('State',v.page_plan.status));section('Page Prompts').append(scoutText('State',v.page_prompts.status));section('Cover Brief').append(scoutText('Local brief',v.cover_brief));const approvals=section('Approvals'),approve=document.createElement('button');approve.type='button';approve.textContent='Approve Book Brief Locally';approve.onclick=async()=>{const route='/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id)+'/approve-brief',body={csrf_token:csrf,confirmed:false},p=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),preview=await p.json();if(!p.ok||!window.confirm(preview.confirmation))return;body.confirmed=true;const r=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});q('coloring-book-status').textContent=r.ok?'Book Brief approved locally. No generation or provider action occurred.':'Approval was not recorded.';if(r.ok)renderProducerProject(id)};approvals.append(scoutText('Book brief',v.book_brief_approval.state),approve,scoutText('External actions',0))}async function loadColoringBookProjects(){const r=await fetch('/app/agency/coloring-book-producer/projects',{cache:'no-store'}),v=await r.json(),root=q('coloring-book-projects');if(!r.ok){q('coloring-book-status').textContent='Install Coloring Book Producer from Marketplace first.';return}root.replaceChildren(...v.projects.map(p=>{const b=document.createElement('button');b.type='button';b.textContent=(p.working_title+' · '+p.concept+' · '+p.status+' · '+p.created_at+' · '+p.candidate_id+(p.duplicate_of?' · superseded duplicate of '+p.duplicate_of:''));b.onclick=()=>renderProducerProject(p.project_id);return b}));if(!v.projects.length)root.textContent='No local projects yet.';else renderProducerProject(v.projects.find(p=>!p.duplicate_of)?.project_id||v.projects[0].project_id)}if(activeView==='agency.coloring-book-producer'){openAgencySection('coloring-book-producer');loadColoringBookProjects()}"
    agency_js += "const baseProducerRender=renderProducerProject;renderProducerProject=async id=>{history.replaceState(null,'','/app?view=agency.coloring-book-producer&project_id='+encodeURIComponent(id));await baseProducerRender(id);const r=await fetch('/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id),{cache:'no-store'}),v=await r.json(),sections=[...q('coloring-book-project').querySelectorAll('section')],plan=sections.find(x=>x.querySelector('h5')?.textContent==='Page Plan'),prompts=sections.find(x=>x.querySelector('h5')?.textContent==='Page Prompts');if(v.project.status==='brief_approved'){const b=document.createElement('button');b.type='button';b.textContent='Generate Page Plan';b.onclick=()=>generatePlan(id);plan.append(b)}if(v.page_plan.status!=='not_generated'){plan.append(scoutText('Page count',v.page_plan.pages.length),scoutText('Plan revision',v.page_plan.plan_revision),scoutText('Current/stale state',v.page_plan.status),scoutText('Page-plan SHA-256',v.page_plan.page_plan_sha256),scoutText('Category distribution',JSON.stringify(v.page_plan.validation.category_distribution)),scoutText('Character distribution',JSON.stringify(v.page_plan.validation.character_distribution)),scoutText('Validation warnings',v.page_plan.validation.warnings.join(' · ')||'none'));const list=document.createElement('div'),pages=v.page_plan.pages;pages.forEach((p,i)=>{const card=document.createElement('article');card.className='agent-card';for(const key of ['title','scene_summary','setting','main_action','complexity']){const f=producerField(key.replaceAll('_',' '),key,p[key]);f.querySelector('input').oninput=e=>p[key]=e.target.value;card.append(f)}const chars=producerField('characters','characters',p.characters.join(', '));chars.querySelector('input').oninput=e=>p.characters=e.target.value.split(',').map(x=>x.trim()).filter(Boolean);card.append(chars);for(const [label,delta] of [['Up',-1],['Down',1]]){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>{const n=i+delta;if(n>=0&&n<pages.length){[pages[i],pages[n]]=[pages[n],pages[i]];savePlan(id,pages)}};card.append(b)}const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.onclick=()=>{pages.splice(i,1);savePlan(id,pages)};const save=document.createElement('button');save.type='button';save.textContent='Save page';save.onclick=()=>savePlan(id,pages);card.append(remove,save);list.append(card)});plan.append(list);const add=document.createElement('button');add.type='button';add.textContent='Add replacement page';add.onclick=()=>{const p=structuredClone(pages.at(-1));p.page_id='page-replacement-'+Date.now();p.prompt_id='prompt-replacement-'+Date.now();p.title='Replacement Page';p.scene_summary='A new original replacement campsite scene.';pages.push(p);savePlan(id,pages)};const approve=document.createElement('button');approve.type='button';approve.textContent='Approve Page Plan Locally';approve.onclick=()=>approvePlan(id);plan.append(add,approve);for(const p of v.page_prompts.prompts){const d=document.createElement('details'),s=document.createElement('summary'),text=document.createElement('p');s.textContent=p.prompt_id+' · '+p.page_id+' · draft';text.textContent=p.positive_prompt+' Avoid: '+p.negative_prompt;d.append(s,text);prompts.append(d)}}};async function generatePlan(id){const route='/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id)+'/generate-page-plan',body={csrf_token:csrf,confirmed:false},p=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),v=await p.json();if(!p.ok){q('coloring-book-status').textContent=v.detail;return}if(v.idempotent){renderProducerProject(id);return}if(!window.confirm('Project '+v.project_id+' · approved brief revision '+v.approved_brief_revision+' · '+v.approved_brief_hash+' · '+v.requested_page_count+' pages · '+v.audience+' · '+v.visual_style+' · '+v.recurring_character_rules+' No images or external actions will occur.'))return;body.confirmed=true;const done=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});q('coloring-book-status').textContent=done.ok?'Page plan generated locally. No images or external actions occurred.':'Page plan was not generated.';if(done.ok){loadColoringBookProjects();renderProducerProject(id)}}async function savePlan(id,pages){const r=await fetch('/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id)+'/page-plan/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,pages})});q('coloring-book-status').textContent=r.ok?'Page plan changes saved locally.':'Page plan changes were not saved.';if(r.ok){loadColoringBookProjects();renderProducerProject(id)}}async function approvePlan(id){const route='/app/agency/coloring-book-producer/projects/'+encodeURIComponent(id)+'/page-plan/approve',body={csrf_token:csrf,confirmed:false},p=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),v=await p.json();if(!p.ok){q('coloring-book-status').textContent=v.detail;return}if(!window.confirm(v.confirmation))return;body.confirmed=true;const r=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),done=await r.json();q('coloring-book-status').textContent=r.ok?done.message:done.detail;if(r.ok){loadColoringBookProjects();renderProducerProject(id)}}const requestedProducerProject=new URLSearchParams(location.search).get('project_id');if(activeView==='agency.coloring-book-producer'&&requestedProducerProject)renderProducerProject(requestedProducerProject)"
    agency_js += ";"
    agency_js=agency_js.replace("else renderProducerProject(v.projects.find(p=>!p.duplicate_of)?.project_id||v.projects[0].project_id)","else renderProducerProject(initialProducerProject||v.projects.find(p=>!p.duplicate_of)?.project_id||v.projects[0].project_id)")
    page=page.replace("<small>This conversation is not saved or added to memory.</small>","").replace("<small>Allows consensual adult conversation and fictional roleplay.</small>","")
    agency_js=agency_js.replace("if(response.ok){agencyRevision=result.revision;", "if(response.ok){if(button.dataset.agentAction==='install'){location.reload();return}agencyRevision=result.revision;")
    agency_js=agency_js.replace("const message=button.dataset.agentAction==='remove'?", "const message=button.dataset.agentAction==='install'?'Install this agent with the displayed local and public read-only permissions?':button.dataset.agentAction==='remove'?")
    extra=agency_js+extra
    policy_js="""const adultPolicy=q('adult-policy'),adultPolicyInput=adultPolicy.elements.adult_mode_available,adultPolicyBefore=adultPolicyInput.checked;bind('edit-adult-policy','click',()=>{adultPolicy.dataset.editing='true';adultPolicyInput.disabled=false;q('edit-adult-policy').hidden=true;q('save-adult-policy').hidden=false;q('cancel-adult-policy').hidden=false});bind('cancel-adult-policy','click',()=>{adultPolicyInput.checked=adultPolicyBefore;adultPolicyInput.disabled=true;adultPolicy.dataset.editing='false';q('edit-adult-policy').hidden=false;q('save-adult-policy').hidden=true;q('cancel-adult-policy').hidden=true});bind('adult-policy','submit',async event=>{event.preventDefault();if(adultPolicy.dataset.editing!=='true')return;const response=await fetch('/app/admin/private-chat-policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,revision:adultPolicy.dataset.revision,adult_mode_available:adultPolicyInput.checked})}),value=await response.json();if(response.ok){adultPolicy.dataset.revision=value.revision;adultPolicyInput.disabled=true;adultPolicy.dataset.editing='false';q('adult-policy-state').textContent=value.adult_mode_available?'Enabled':'Disabled';q('edit-adult-policy').hidden=false;q('save-adult-policy').hidden=true;q('cancel-adult-policy').hidden=true}});"""
    extra="""const reviewArtwork=q('review-artwork-preview'),reviewFallback=q('review-artwork-fallback'),reviewStage=q('review-preview-stage');if(reviewArtwork&&reviewFallback)reviewArtwork.addEventListener('error',()=>{reviewArtwork.hidden=true;reviewFallback.hidden=false});document.querySelectorAll('[data-gallery-src]').forEach(button=>button.onclick=()=>{if(!reviewArtwork)return;reviewArtwork.hidden=false;reviewFallback.hidden=true;reviewArtwork.src=button.dataset.gallerySrc;q('gallery-selected-label').textContent=button.dataset.galleryLabel});document.querySelectorAll('[data-preview-background]').forEach(button=>button.onclick=()=>{if(!reviewStage)return;const value=button.dataset.previewBackground;reviewStage.dataset.background=value;reviewStage.style.background=value==='light'?'#f4f0e8':value==='transparency'?'repeating-conic-gradient(#bbb 0 25%,#eee 0 50%) 0/24px 24px':'#17191d'});document.querySelectorAll('[data-copy-target]').forEach(button=>button.onclick=()=>navigator.clipboard?.writeText(q(button.dataset.copyTarget)?.textContent||''));"""+policy_js+extra
    publish_js="""const publishButton=q('approve-and-publish'),finalReview=q('final-review-panel'),publicationStatus=q('publication-action-status');let publicationBusy=false;async function publicationJson(response){try{return await response.json()}catch(e){return {detail:'The server returned an unreadable response.'}}}if(publishButton&&finalReview)publishButton.onclick=async()=>{if(publicationBusy)return;publicationBusy=true;publishButton.disabled=true;publicationStatus.textContent='Preparing publication confirmation…';const route='/app/commerce/jobs/'+encodeURIComponent(selectedJob)+'/approve-and-publish';let preview;try{preview=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,confirmed:false})})}catch(e){publicationStatus.textContent='Confirmation preview could not be reached. Nothing was published.';publicationBusy=false;publishButton.disabled=false;return}const proposed=await publicationJson(preview);if(!preview.ok){publicationStatus.textContent='Confirmation preview failed (HTTP '+preview.status+'): '+(proposed.detail||'Nothing was published.');publicationBusy=false;publishButton.disabled=false;return}if(!window.confirm(proposed.confirmation)){publicationStatus.textContent='Publication canceled. Nothing was published.';publicationBusy=false;publishButton.disabled=false;return}publicationStatus.textContent='Publishing…';let response;try{response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,confirmed:true,review_identity:proposed.review_identity,revision_number:proposed.revision_number,destination:proposed.destination})})}catch(e){publicationStatus.textContent='Publication result is uncertain because the server response was interrupted. Do not retry automatically.';return}const value=await publicationJson(response);if(!response.ok){publicationStatus.textContent='Publication failed (HTTP '+response.status+'): '+(value.detail||'The existing draft was preserved. Do not retry until the result is verified.');return}if(value.publication_performed){publicationStatus.textContent='Published. Refreshing final publication state…';location.replace('/app?view=commerce.review&job_id='+encodeURIComponent(selectedJob));return}publicationStatus.textContent='Publication is pending safe reconciliation. Do not submit again.'}"""
    mockup_js="""const mockupGallery=q('mockup-intake-gallery'),mockupStatus=q('mockup-intake-status');if(mockupGallery){mockupGallery.querySelectorAll('[data-mockup-up]').forEach(b=>b.onclick=()=>{const n=b.closest('[data-mockup-asset]');if(n.previousElementSibling)mockupGallery.insertBefore(n,n.previousElementSibling)});mockupGallery.querySelectorAll('[data-mockup-down]').forEach(b=>b.onclick=()=>{const n=b.closest('[data-mockup-asset]');if(n.nextElementSibling)mockupGallery.insertBefore(n.nextElementSibling,n)});mockupGallery.querySelectorAll('[data-mockup-remove]').forEach(b=>b.onclick=()=>b.closest('[data-mockup-asset]').remove())}bind('refresh-printify-mockups','click',async()=>{mockupStatus.textContent='Reading current Printify product mockups…';const r=await fetch('/app/commerce/jobs/'+encodeURIComponent(selectedJob)+'/mockup-intake/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf})}),v=await publicationJson(r);mockupStatus.textContent=r.ok?(v.sync_warning||('Imported '+v.mockups.length+' Printify mockups. Reloading review…')):('Mockup intake failed (HTTP '+r.status+'): '+(v.detail||'No provider write occurred.'));if(r.ok)location.reload()});bind('approve-mockups-locally','click',async()=>{const cards=[...mockupGallery.querySelectorAll('[data-mockup-asset]')],primary=mockupGallery.querySelector('input[name=mockup-primary]:checked')?.closest('[data-mockup-asset]'),ordered=cards.map(n=>({asset_id:n.dataset.mockupAsset,role:n.querySelector('[data-mockup-role]').value}));if(primary){const i=ordered.findIndex(x=>x.asset_id===primary.dataset.mockupAsset);ordered.unshift(...ordered.splice(i,1))}const route='/app/commerce/jobs/'+encodeURIComponent(selectedJob)+'/mockup-intake/approve',preview=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,confirmed:false,selections:ordered})}),v=await publicationJson(preview);if(!preview.ok){mockupStatus.textContent='Local mockup review failed (HTTP '+preview.status+'): '+(v.detail||'Etsy was not updated.');return}if(!window.confirm(v.message))return;const r=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,confirmed:true,selections:ordered})}),done=await publicationJson(r);mockupStatus.textContent=r.ok?'Mockups approved locally. Etsy has not been updated.':('Local approval failed (HTTP '+r.status+'): '+(done.detail||'Etsy was not updated.'))})"""
    composer_js="""const composedGallery=q('composed-mockup-gallery'),composerStatus=q('composer-status');if(composedGallery){composedGallery.querySelectorAll('[data-composed-up]').forEach(b=>b.onclick=()=>{const n=b.closest('[data-composed-asset]');if(n.previousElementSibling)composedGallery.insertBefore(n,n.previousElementSibling)});composedGallery.querySelectorAll('[data-composed-down]').forEach(b=>b.onclick=()=>{const n=b.closest('[data-composed-asset]');if(n.nextElementSibling)composedGallery.insertBefore(n.nextElementSibling,n)});composedGallery.querySelectorAll('[data-composed-remove]').forEach(b=>b.onclick=()=>b.closest('[data-composed-asset]').remove());composedGallery.querySelectorAll('[data-composed-regenerate]').forEach(b=>b.onclick=()=>{const n=b.closest('[data-composed-asset]'),role=n.querySelector('strong').textContent;document.querySelector('[data-compose-role="'+role+'"]').click()})}document.querySelectorAll('[data-compose-role]').forEach(button=>button.onclick=async()=>{const role=button.dataset.composeRole,select=document.querySelector('[data-composer-role="'+role+'"]'),parts=select.value.split('@');if(parts.length!==2){composerStatus.textContent='Select a compatible registered template.';return}composerStatus.textContent='Compositing exact approved artwork locally…';const r=await fetch('/app/commerce/jobs/'+encodeURIComponent(selectedJob)+'/mockup-composer/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,role,template_id:parts[0],version:parts[1]})}),v=await publicationJson(r);composerStatus.textContent=r.ok?'Local mockup composed. Etsy and Printify were not updated.':('Composition failed (HTTP '+r.status+'): '+(v.detail||'No external action occurred.'));if(r.ok)location.reload()});bind('approve-composed-mockups','click',async()=>{const cards=[...composedGallery.querySelectorAll('[data-composed-asset]')],ids=cards.map(n=>n.dataset.composedAsset),primary=composedGallery.querySelector('input[name=composed-primary]:checked')?.closest('[data-composed-asset]')?.dataset.composedAsset,route='/app/commerce/jobs/'+encodeURIComponent(selectedJob)+'/mockup-composer/approve',body={csrf_token:csrf,ordered_ids:ids,primary_id:primary,confirmed:false},preview=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),v=await publicationJson(preview);if(!preview.ok){composerStatus.textContent='Local approval failed (HTTP '+preview.status+'): '+(v.detail||'No external action occurred.');return}if(!window.confirm(v.message))return;body.confirmed=true;const r=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});composerStatus.textContent=r.ok?'Mockups approved locally. Etsy and Printify have not been updated.':'Local approval failed. Etsy and Printify were not updated.'})"""
    extra=composer_js+";"+extra
    extra=mockup_js+";"+extra
    extra=publish_js+";"+extra
    extra=extra.replace("q('dashboard-work').textContent=", "q('dashboard-attention').textContent='Failed commerce jobs: '+v.work.failed.length+' · Pending confirmations: '+v.work.pending_confirmations+' · Degraded services: '+v.systems.filter(x=>x.status!=='healthy').length;q('dashboard-work').textContent=")
    page=page.replace("loadAccessStatus();document.documentElement.dataset.jamesosReady='true';", "loadAccessStatus();"+extra+"document.documentElement.dataset.jamesosReady='true';")
    page=page.replace("if(status.ready_for_review){navigate('commerce.review');return}", "if(status.ready_for_review){location.replace('/app?view=commerce.review&job_id='+encodeURIComponent(selectedJob));return}")
    page=page.replace("if(status.failed){navigate('diagnostics');q('generic-copy').textContent=status.failure_message_safe||'Product preparation did not complete.';return}", "if(status.failed){sessionStorage.setItem('jamesos-safe-job-failure',status.failure_message_safe||'Product preparation did not complete.');location.replace('/app?view=commerce.diagnostics&job_id='+encodeURIComponent(selectedJob));return}")
    page=page.replace("q('job-status').textContent=status.progress_label||status.stage;", "const progress=status.progress_label||status.stage||'Preparing product';q('job-status').textContent=progress;if(activeView==='commerce.loading')q('generic-copy').textContent=progress+' — JamesOS is preparing an unpublished draft for human review.';")
    page=page.replace("if(selectedJob)watchJob();let healthState", "if(selectedJob&&activeView==='commerce.loading')watchJob();let healthState")
    page=page.replace("href='/commerce/new'","href='/app?view=commerce.new'")
    return _commerce_ui_response(page)


@app.get("/app/chat-diagnostics")
def application_shell_chat_diagnostics_route(request:Request):
    _require_local(request)
    try:ollama_readiness()
    except Exception:pass
    diagnostic=chat_diagnostics()
    return JSONResponse({"readiness":diagnostic["readiness"],"generation":diagnostic["generation"],"application_shell":application_shell_diagnostics()},headers={"Cache-Control":"no-store"})


@app.get("/app/agency")
def application_agency_registry_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    return JSONResponse(ShellAgencyRegistry().snapshot(),headers={"Cache-Control":"no-store"})


@app.get("/app/agency/agents/{agent_id}")
def application_agency_agent_route(agent_id:str,request:Request):
    _require_local(request)
    try:return JSONResponse(ShellAgencyRegistry().details(agent_id),headers={"Cache-Control":"no-store"})
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    except LookupError as exc:raise HTTPException(status_code=404,detail="Agent is not installed") from exc


@app.post("/app/agency/agents/{agent_id}/{action}")
async def application_agency_mutation_route(agent_id:str,action:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ShellAgencyRegistry().mutate(agent_id,action,confirmed=values.get("confirmed") is True,revision=int(values.get("revision",-1)))
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
    except LookupError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
    except (TypeError,ValueError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.get("/app/agency/book-scout/runs")
def application_book_scout_runs_route(request:Request):
    _require_local(request);return JSONResponse({"runs":BookOpportunityScoutService().list_runs()},headers={"Cache-Control":"no-store"})


@app.get("/app/agency/book-scout/runs/{run_id}")
def application_book_scout_run_route(run_id:str,request:Request):
    _require_local(request)
    try:return JSONResponse(BookOpportunityScoutService().load(run_id),headers={"Cache-Control":"no-store"})
    except (ValueError,FileNotFoundError) as exc:raise HTTPException(status_code=404,detail="Research run not found") from exc


@app.post("/app/agency/book-scout/runs")
async def application_book_scout_start_route(request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.pop("csrf_token","") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return BookOpportunityScoutService().run(values)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.post("/app/agency/book-scout/runs/{run_id}/candidates/{candidate_id}/decision")
async def application_book_scout_decision_route(run_id:str,candidate_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return BookOpportunityScoutService().decide(run_id,candidate_id,str(values.get("action") or ""),confirmed=values.get("confirmed") is True,reason=str(values.get("reason") or ""))
    except FileNotFoundError as exc:raise HTTPException(status_code=404,detail="Research run not found") from exc
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


def _require_coloring_book_producer():
    item=next((x for x in ShellAgencyRegistry().snapshot()["agents"] if x["agent_id"]=="jamesos.coloring-book-producer"),None)
    if not item or item["enabled_state"]!="enabled":raise HTTPException(status_code=403,detail="Coloring Book Producer is not installed and enabled")

@app.get("/app/agency/coloring-book-producer/projects")
def coloring_book_projects_route(request:Request):_require_local(request);_require_coloring_book_producer();return {"projects":ColoringBookProducer().list(),"external_actions":0}

@app.get("/app/agency/coloring-book-producer/projects/{project_id}")
def coloring_book_project_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer()
    try:return ColoringBookProducer().load(project_id)
    except (ValueError,OSError,KeyError,json.JSONDecodeError):raise HTTPException(status_code=404,detail="Book project unavailable")

@app.post("/app/agency/coloring-book-producer/projects/{project_id}/edit")
async def coloring_book_project_edit_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().update(project_id,values.get("book_brief"),values.get("production_spec"))
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc

@app.post("/app/agency/coloring-book-producer/projects/{project_id}/approve-brief")
async def coloring_book_project_approve_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().approve_brief(project_id,confirmed=values.get("confirmed") is True)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc

@app.post("/app/agency/coloring-book-producer/projects/{project_id}/generate-page-plan")
async def coloring_book_generate_plan_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().generate_page_plan(project_id,confirmed=values.get("confirmed") is True,regenerate=values.get("regenerate") is True)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc

@app.post("/app/agency/coloring-book-producer/projects/{project_id}/page-plan/edit")
async def coloring_book_edit_plan_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().edit_page_plan(project_id,values.get("pages"))
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc

@app.post("/app/agency/coloring-book-producer/projects/{project_id}/page-plan/approve")
async def coloring_book_approve_plan_route(project_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().approve_page_plan(project_id,confirmed=values.get("confirmed") is True)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc

@app.post("/app/agency/book-scout/runs/{run_id}/candidates/{candidate_id}/create-project")
async def coloring_book_create_route(run_id:str,candidate_id:str,request:Request):
    _require_local(request);_require_coloring_book_producer();_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return ColoringBookProducer().create(run_id,candidate_id,values.get("configuration"),confirmed=values.get("confirmed") is True)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as exc:raise HTTPException(status_code=422,detail=str(exc)[:300]) from exc


@app.post("/app/chat")
async def application_shell_chat_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/json":raise HTTPException(status_code=415,detail="JSON required")
    values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    profiles=list_commerce_profiles(enabled_only=True);profile_id=str(values.get("active_profile_id") or "");profile=next((item for item in profiles if str(item.get("profile_id") or "")==profile_id),None)
    if profile is None:raise HTTPException(status_code=422,detail="Enabled profile required")
    try:attachments=verify_attachments(str(values.get("conversation_id") or ""),values.get("attachments",[]))
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    try:attachment_receipts,attachment_context=process_chat_attachments(str(values.get("conversation_id") or ""),attachments)
    except Exception as exc:raise HTTPException(status_code=422,detail="An attachment could not be processed safely.") from exc
    workspace={"active_view":values.get("active_view"),"selected_job_id":values.get("selected_job_id"),"form":values.get("form") if isinstance(values.get("form"),dict) else {},"attachments":attachments,"attachment_receipts":attachment_receipts,"attachment_context":attachment_context}
    private_mode=values.get("ephemeral") is True and values.get("private_mode") is True
    adult_mode=values.get("adult_mode") is True
    if adult_mode and (not private_mode or not PrivateChatPolicy().status()["adult_mode_available"] or not validate_adult_session(values.get("adult_consent_session"))):raise HTTPException(status_code=403,detail="Adult mode requires an available private session with current-session affirmation.")
    if values.get("adult_mode") not in (None,False,True) or values.get("ephemeral") not in (None,False,True):raise HTTPException(status_code=422,detail="Invalid private-chat state.")
    result=WorkspaceChatService().message(conversation_id=str(values.get("conversation_id") or ""),message=str(values.get("message") or ""),profile=profile,profiles=profiles,workspace=workspace,ephemeral=private_mode,adult_mode=adult_mode)
    if private_mode:
        for item in attachments:
            try:delete_pending_attachment(str(values.get("conversation_id") or ""),str(item.get("attachment_id") or ""))
            except (ValueError,OSError):pass
    return result


@app.post("/app/private-session/affirm")
async def application_private_session_affirm_route(request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    if values.get("affirmed_18_plus") is not True or not PrivateChatPolicy().status()["adult_mode_available"]:raise HTTPException(status_code=403,detail="Adult mode is unavailable or was not affirmed.")
    return JSONResponse(affirm_adult_session(),headers={"Cache-Control":"no-store"})


@app.post("/app/private-session/end")
async def application_private_session_end_route(request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    end_adult_session(values.get("adult_consent_session"));return {"ended":True}


@app.get("/app/admin/private-chat-policy")
def application_private_chat_policy_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    return JSONResponse(PrivateChatPolicy().status(),headers={"Cache-Control":"no-store"})


@app.post("/app/admin/private-chat-policy")
async def application_private_chat_policy_save_route(request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return PrivateChatPolicy().save(available=values.get("adult_mode_available"),revision=str(values.get("revision") or ""))
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.post("/app/attachments")
async def application_shell_attachment_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if not request.headers.get("content-type","").startswith("multipart/form-data"):raise HTTPException(status_code=415,detail="Multipart form required")
    form=await request.form();token=str(form.get("csrf_token") or "")
    if not hmac.compare_digest(token,_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    upload=form.get("file");conversation_id=str(form.get("conversation_id") or "")
    if upload is None or not callable(getattr(upload,"read",None)):raise HTTPException(status_code=422,detail="One file is required")
    try:data=await upload.read(MAX_BYTES+1)
    finally:await upload.close()
    try:return store_attachment(conversation_id=conversation_id,filename=upload.filename or "attachment",content_type=(upload.content_type or "").casefold(),data=data)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@app.delete("/app/attachments/{attachment_id}")
async def application_shell_attachment_delete_route(attachment_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/json":raise HTTPException(status_code=415,detail="JSON required")
    values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:removed=delete_pending_attachment(str(values.get("conversation_id") or ""),attachment_id)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
    return {"removed":removed}


@app.get("/app/layouts/{view_id}")
def application_layout_get_route(view_id:str,request:Request):
    _require_local(request);return JSONResponse(LayoutManager().get(view_id),headers={"Cache-Control":"no-store"})


@app.put("/app/layouts/{view_id}")
async def application_layout_put_route(view_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/json":raise HTTPException(status_code=415,detail="JSON required")
    value=await request.json();token=str(value.pop("csrf_token","") if isinstance(value,dict) else "")
    if not hmac.compare_digest(token,_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    return JSONResponse(LayoutManager().save(view_id,value),headers={"Cache-Control":"no-store"})


@app.delete("/app/layouts/{view_id}")
async def application_layout_delete_route(view_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    value=await request.json() if request.headers.get("content-type","").split(";",1)[0]=="application/json" else {}
    if not hmac.compare_digest(str(value.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    return JSONResponse(LayoutManager().reset(view_id),headers={"Cache-Control":"no-store"})


@app.get("/commerce/new",response_class=HTMLResponse)
def commerce_new_route(request:Request):
    _require_local(request)
    return RedirectResponse("/app?view=commerce.new",status_code=303,headers={"Cache-Control":"no-store"})
    cards=[];profiles=list_commerce_profiles(enabled_only=True);selected=selected_profile_id()
    if selected not in {str(item.get("profile_id") or "") for item in profiles}:selected=str((profiles[0] if profiles else {}).get("profile_id") or "")
    for profile in profiles:
        config=profile.get("configuration") or {};pid=html_escape(str(profile.get("profile_id") or ""),quote=True);display=html_escape(str(profile.get("display_name") or pid));shop=html_escape(str(config.get("printify_shop_title") or display));slug=html_escape(str(config.get("etsy_shop_slug") or ""));shop_id=int(config["printify_shop_id"])
        cards.append(f"<label class='card'><input type='radio' name='commerce_profile_id' value='{pid}' data-printify-title='{shop}' data-shop-id='{shop_id}' data-etsy='{slug}' {'checked' if str(profile.get('profile_id') or '')==selected else ''} required><strong>{display}</strong><br>Profile: {pid}<br>Printify: {shop} — {shop_id}<br>Etsy: {slug}</label>")
    page=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>New commerce product</title><style>body{font:16px system-ui;max-width:1200px;margin:auto;padding:2rem}.layout{display:grid;grid-template-columns:minmax(300px,.8fr) minmax(420px,1.2fr);gap:1.5rem}.copilot,.product{border:2px solid #ccd;padding:1rem;border-radius:12px}.cards{display:grid;gap:1rem}.card{border:2px solid #ccd;padding:1rem;border-radius:10px}textarea,input[type=text]{width:100%;box-sizing:border-box;margin:.4rem 0 1rem;padding:.6rem}.actions{display:flex;flex-wrap:wrap;gap:.4rem}.transcript{max-height:15rem;overflow:auto;border-top:1px solid #ccd;margin-top:1rem}.turn{padding:.5rem 0;border-bottom:1px solid #eef}.status{min-height:1.5rem}.drawer-toggle{display:none}@media(max-width:760px){body{padding:1rem}.layout{display:block}.drawer-toggle{display:block}.copilot[hidden]{display:none}.product{margin-top:1rem}}</style>"
        f"<button type='button' class='drawer-toggle' id='copilot-toggle'>JamesOS Product Studio</button><main class='layout'><aside class='copilot' id='copilot' data-request-state='idle'><h1>JamesOS Product Studio</h1><p>Build your design brief, artwork direction, and Etsy listing.</p><p>Desktop-local suggestions only. Product Studio cannot contact shops or submit this form.</p><textarea id='copilot-message' maxlength='2000' placeholder='Ask for a phrase, brief, title, colors, tags, review, or validation help'></textarea><button type='button' id='copilot-send'>Ask Product Studio</button><p class='status' id='copilot-status' aria-live='polite'>Ready.</p><p id='copilot-response'></p><div id='copilot-suggestions'></div><p id='copilot-colors'></p><p id='copilot-artwork'></p><p id='copilot-tags'></p><div class='actions' id='copilot-actions'></div><div class='transcript' id='copilot-transcript' aria-label='Recent Product Studio conversation'></div></aside><section class='product'><h1>New Commerce Product</h1><form id='commerce-form' method='post' action='/commerce/new'><input type='hidden' name='csrf_token' value='{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}'><div class='cards'>{''.join(cards)}</div>"
        "<label>Exact phrase<textarea id='exact_phrase' name='exact_phrase' maxlength='500'></textarea></label><label>Product brief<textarea id='product_brief' name='product_brief' maxlength='5000' required></textarea></label><label>Listing title<input id='listing_title' type='text' name='listing_title' maxlength='140'></label><label>Special instructions<textarea id='special_instructions' name='special_instructions' maxlength='3000'></textarea></label>"
        "<input type='hidden' name='destination_confirmed' value='true'><button id='generate'>Generate unpublished draft</button><p id='destination'></p></form></section></main><script>const csrf='__PRODUCT_STUDIO_CSRF__',r=[...document.querySelectorAll('input[name=commerce_profile_id]')],b=document.getElementById('generate'),d=document.getElementById('destination'),fields=['exact_phrase','product_brief','listing_title','special_instructions'],studio=document.getElementById('copilot'),send=document.getElementById('copilot-send'),box=document.getElementById('copilot-message'),status=document.getElementById('copilot-status');let session=crypto.randomUUID(),suggestions={},inFlight=false,turns=[];function u(){const x=r.find(x=>x.checked);if(x){b.textContent='Generate unpublished draft in '+x.dataset.etsy;d.textContent='Printify: '+x.dataset.printifyTitle+' — '+x.dataset.shopId+' | Etsy: '+x.dataset.etsy;session=crypto.randomUUID();turns=[];transcript()}}r.forEach(x=>x.addEventListener('change',u));u();document.getElementById('copilot-toggle').onclick=()=>{const c=document.getElementById('copilot');c.hidden=!c.hidden};function state(name,text){studio.dataset.requestState=name;status.textContent=text}function apply(k){if(suggestions[k]!==undefined)document.getElementById(k).value=suggestions[k]}function buttons(){const a=document.getElementById('copilot-actions');a.replaceChildren();for(const [label,key] of [['Apply exact phrase','exact_phrase'],['Apply product brief','product_brief'],['Apply listing title','listing_title'],['Apply special instructions','special_instructions'],['Apply all','all']]){let q=document.createElement('button');q.type='button';q.textContent=label;q.onclick=()=>key==='all'?fields.forEach(apply):apply(key);a.appendChild(q)}}function transcript(){const t=document.getElementById('copilot-transcript');t.replaceChildren();turns.slice(-6).forEach(x=>{let p=document.createElement('p');p.className='turn';p.textContent='You: '+x.user+'\\nProduct Studio: '+x.assistant;t.appendChild(p)})}send.onclick=async()=>{if(inFlight)return;const message=box.value.trim();if(!message){state('failed','Enter a request for Product Studio.');return}inFlight=true;box.disabled=true;send.disabled=true;send.textContent='Thinking…';state('submitting','Thinking…');await new Promise(requestAnimationFrame);const x=r.find(x=>x.checked),form=Object.fromEntries(fields.map(k=>[k,document.getElementById(k).value]));try{state('generating','Preparing suggestions…');const response=await fetch('/commerce/copilot/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf_token:csrf,session_id:session,profile_id:x.value,message,form})});let data={};try{data=await response.json()}catch(e){}if(!response.ok)throw new Error(data.message||'Product Studio could not complete that request. Please try again.');suggestions=data.suggestions||{};const visible=(data.safe_warning?data.safe_warning+' ':'')+(data.message||'');document.getElementById('copilot-response').textContent=visible;document.getElementById('copilot-colors').textContent='Garment colors: '+(suggestions.garment_colors||[]).join(', ');document.getElementById('copilot-artwork').textContent='Artwork palette: '+(suggestions.artwork_palette||[]).join(', ');document.getElementById('copilot-tags').textContent=(data.tags_valid?'13 validated tags: ':'Tags need review: ')+(suggestions.listing_tags||[]).join(', ');const detail=document.getElementById('copilot-suggestions');detail.textContent=['Exact phrase: '+(suggestions.exact_phrase||''),'Product brief: '+(suggestions.product_brief||''),'Listing title: '+(suggestions.listing_title||''),'Special instructions: '+(suggestions.special_instructions||'')].join('\\n');buttons();turns.push({user:message,assistant:visible});transcript();state(data.safe_warning?'failed':'completed',data.safe_warning?'Product Studio unavailable: model response required a local fallback.':'Suggestions ready')}catch(e){const safe=e.message||'Product Studio could not complete that request. Please try again.';document.getElementById('copilot-response').textContent=safe;state('failed','Product Studio unavailable: '+safe)}finally{inFlight=false;box.disabled=false;send.disabled=false;send.textContent='Ask Product Studio'}}</script>")
    page=page.replace("__PRODUCT_STUDIO_CSRF__",html_escape(_COMMERCE_CREATE_CSRF,quote=True))
    return _commerce_ui_response(page)


@app.post("/commerce/copilot/message")
async def commerce_copilot_message_route(request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/json":raise HTTPException(status_code=415,detail="JSON required")
    values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    profile=load_commerce_profile_by_id(str(values.get("profile_id") or ""),required=True)
    return CommerceCopilotService().message(session_id=str(values.get("session_id") or ""),profile=profile,message=str(values.get("message") or ""),form=values.get("form") if isinstance(values.get("form"),dict) else {})


@app.post("/commerce/new")
async def commerce_new_submit(request:Request,background_tasks:BackgroundTasks):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/x-www-form-urlencoded":raise HTTPException(status_code=415,detail="Form encoding required")
    values={key:items[-1] for key,items in parse_qs((await request.body()).decode(),keep_blank_values=True).items()}
    if not hmac.compare_digest(values.get("csrf_token",""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    service=CommerceCreationService()
    try:result=service.create_job(commerce_profile_id=values.get("commerce_profile_id",""),exact_phrase=values.get("exact_phrase",""),product_brief=values.get("product_brief",""),listing_title=values.get("listing_title",""),special_instructions=values.get("special_instructions",""),destination_confirmed=values.get("destination_confirmed")=="true",request_id=request.headers.get("x-request-id"))
    except JamesOSError as exc:
        if exc.stage!="product_brief_preflight":raise
        handle_error(exc,operation="commerce_creation.preflight",context={"commerce_profile_id":values.get("commerce_profile_id")},request_id=request.headers.get("x-request-id"))
        page=application_shell_route(request).body.decode("utf-8")
        replacements={
            "<textarea id='exact_phrase' name='exact_phrase' maxlength='500'></textarea>":f"<textarea id='exact_phrase' name='exact_phrase' maxlength='500'>{html_escape(values.get('exact_phrase',''))}</textarea>",
            "<textarea id='product_brief' name='product_brief' maxlength='5000' required></textarea>":f"<textarea id='product_brief' name='product_brief' maxlength='5000' required>{html_escape(values.get('product_brief',''))}</textarea>",
            "<input id='listing_title' type='text' name='listing_title' maxlength='140'>":f"<input id='listing_title' type='text' name='listing_title' maxlength='140' value='{html_escape(values.get('listing_title',''),quote=True)}'>",
            "<textarea id='special_instructions' name='special_instructions' maxlength='3000'></textarea>":f"<textarea id='special_instructions' name='special_instructions' maxlength='3000'>{html_escape(values.get('special_instructions',''))}</textarea>",
            "<section id='commerce-new' class='layout-grid'>":f"<section id='commerce-new' class='layout-grid'><p role='alert'><strong>{html_escape(exc.user_message)}</strong> No artwork or provider work was started.</p>",
        }
        for old,new in replacements.items():page=page.replace(old,new)
        page=re.sub(r"(<input type='radio' name='commerce_profile_id'[^>]*?) checked(?=[^>]*>)",r"\1",page)
        selected=html_escape(values.get("commerce_profile_id",""),quote=True)
        page=page.replace(f"<input type='radio' name='commerce_profile_id' value='{selected}'",f"<input type='radio' name='commerce_profile_id' value='{selected}' checked",1)
        return _commerce_ui_response(page,status_code=422)
    background_tasks.add_task(service.run_generation_safely,result["job_id"])
    return RedirectResponse(f"/app?view=commerce.loading&job_id={result['job_id']}",status_code=303,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})


@app.get("/commerce/jobs/{job_id}/loading",response_class=HTMLResponse)
def commerce_loading_route(job_id:str,request:Request):
    _require_local(request);status=CommerceCreationService().safe_status(job_id)
    page=(f"<!doctype html><meta charset='utf-8'><h1>Creating product</h1><p><strong>Brand:</strong> {html_escape(str(status['brand_display_name']))}</p><p><strong>Printify destination:</strong> {html_escape(str(status['printify_shop_title']))} — {int(status['printify_shop_id'])}</p><p><strong>Etsy destination:</strong> {html_escape(str(status['etsy_shop_slug']))}</p><p id='step'><strong>Current step:</strong> {html_escape(str(status['progress_label']))}</p>"
        f"<form id='open-review-form' method='post' action='/commerce/jobs/{html_escape(job_id,quote=True)}/open-review' style='display:none'><input type='hidden' name='csrf_token' value='{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}'><button type='submit'>Continue to product review</button></form><noscript><style>#open-review-form{{display:block!important}}</style></noscript>"
        f"<section id='failure' hidden><h2 id='outcome-title'>Preparation paused</h2><p id='failure-message'></p><p id='last-stage'></p><p id='product-id'></p><p id='draft-state'></p><p id='terminal-state'><strong>UNPUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p><form id='resume-form' hidden method='post' action='/commerce/jobs/{html_escape(job_id,quote=True)}/resume-existing-draft'><input type='hidden' name='csrf_token' value='{html_escape(_COMMERCE_CREATE_CSRF,quote=True)}'><button type='submit'>Resume using existing draft</button></form><p id='manual' hidden><strong>Manual verification required</strong><br>Do not retry automatically.</p><p><a href='/app?view=commerce.new'>Return to Product Studio</a></p></section><p id='safety'><strong>UNPUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p>"
        f"<script>let openingReview=false;async function p(){{let r=await fetch('/commerce/jobs/{html_escape(job_id,quote=True)}/status.json',{{cache:'no-store'}}),s=await r.json();document.getElementById('step').textContent='Current step: '+s.progress_label;if(s.open_product_review_allowed||s.ready_for_review){{if(!openingReview){{openingReview=true;document.getElementById('open-review-form').requestSubmit()}}return}}if(s.failed){{document.getElementById('failure').hidden=false;document.getElementById('safety').hidden=true;const uncertain=s.terminal_outcome==='uncertain';document.getElementById('outcome-title').textContent=uncertain?'Manual verification required':'Preparation paused';document.getElementById('failure-message').textContent=uncertain?'Do not retry automatically.':(s.failure_message_safe||'Product preparation did not complete.');document.getElementById('last-stage').textContent='Last completed stage: '+(s.last_completed_stage||'none');document.getElementById('product-id').textContent=s.printify_product_id?'Printify product ID: '+s.printify_product_id:'';document.getElementById('draft-state').textContent=s.printify_draft_exists?'Printify draft exists':'No Printify draft exists';document.getElementById('terminal-state').innerHTML='<strong>'+String(s.publication_status||'not_published').toUpperCase()+'</strong><br><strong>'+String(s.order_status||'not_created').replaceAll('_',' ').toUpperCase()+'</strong>';document.getElementById('resume-form').hidden=!s.resume_existing_draft_allowed;document.getElementById('manual').hidden=!s.manual_verification_required}}else setTimeout(p,1500)}}setTimeout(p,500)</script>")
    return _commerce_ui_response(page)


@app.post("/commerce/jobs/{job_id}/open-review")
async def commerce_open_review_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/x-www-form-urlencoded":raise HTTPException(status_code=415,detail="Form encoding required")
    values={key:items[-1] for key,items in parse_qs((await request.body()).decode(),keep_blank_values=True).items()}
    if not hmac.compare_digest(values.get("csrf_token",""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:result=CommerceCreationService().open_product_review(job_id)
    except JamesOSError as exc:
        handle_error(exc,operation="commerce_creation.open_review",context={"job_id":job_id})
        message=html_escape(str(exc.user_message or "Product review could not be opened safely."));job=html_escape(job_id,quote=True)
        return _commerce_ui_response(f"<!doctype html><meta charset='utf-8'><h1>Product review unavailable</h1><p>{message}</p><p><strong>UNPUBLISHED</strong><br><strong>NO ORDER CREATED</strong></p><a href='/commerce/jobs/{job}/loading'>Return to product status</a>",409)
    return RedirectResponse(result["review_url"],status_code=303,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})


@app.post("/commerce/jobs/{job_id}/resume-existing-draft")
async def commerce_resume_existing_draft_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request)
    if request.headers.get("content-type","").split(";",1)[0]!="application/x-www-form-urlencoded":raise HTTPException(status_code=415,detail="Form encoding required")
    values={key:items[-1] for key,items in parse_qs((await request.body()).decode(),keep_blank_values=True).items()}
    if not hmac.compare_digest(values.get("csrf_token",""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    service=CommerceCreationService();status=service.safe_status(job_id)
    if status.get("open_product_review_allowed") or not status.get("resume_existing_draft_allowed"):
        return RedirectResponse(f"/commerce/jobs/{job_id}/loading",status_code=303,headers={"Cache-Control":"no-store"})
    try:result=service.resume_existing_draft(job_id)
    except JamesOSError as exc:
        handle_error(exc,operation="commerce_creation.resume",context={"job_id":job_id})
        return RedirectResponse(f"/commerce/jobs/{job_id}/loading",status_code=303,headers={"Cache-Control":"no-store"})
    return RedirectResponse(result["review_url"],status_code=303,headers={"Cache-Control":"no-store"})


@app.get("/commerce/jobs/{job_id}/resume-existing-draft")
def commerce_resume_existing_draft_get_route(job_id:str,request:Request):
    _require_local(request);return RedirectResponse(f"/commerce/jobs/{job_id}/loading",status_code=303,headers={"Cache-Control":"no-store"})


@app.get("/commerce/jobs/{job_id}/status.json")
def commerce_loading_status_route(job_id:str,request:Request):
    _require_local(request);return JSONResponse(CommerceCreationService().safe_status(job_id),headers={"Cache-Control":"no-store"})


@app.get("/commerce/jobs/{job_id}/artwork-preview")
def commerce_artwork_preview_route(job_id:str,request:Request):
    _require_read_only_asset(request);service=CommerceCreationService()
    try:snapshot=service.review_snapshot(job_id);state=service.orchestrator.load(job_id)
    except (FileNotFoundError,KeyError,ValueError):raise HTTPException(status_code=404,detail="Artwork preview unavailable")
    selected=(((state.get("evidence") or {}).get("selection") or {}).get("selected") or {});stored_path=selected.get("png_path")
    if not isinstance(stored_path,str) or not stored_path:raise HTTPException(status_code=404,detail="Artwork preview unavailable")
    path=Path(stored_path);root=service.orchestrator._path(job_id).parent.resolve()
    try:resolved=path.resolve(strict=True)
    except OSError:raise HTTPException(status_code=404,detail="Artwork preview unavailable")
    if root not in resolved.parents or not resolved.is_file():raise HTTPException(status_code=403,detail="Artwork preview forbidden")
    if snapshot.get("selected_candidate_id")!=selected.get("candidate_id") or resolved.suffix.casefold()!=".png":raise HTTPException(status_code=404,detail="Artwork preview unavailable")
    try:
        with Image.open(resolved) as image:image.verify();valid=image.format=="PNG"
    except (OSError,ValueError):valid=False
    if not valid:raise HTTPException(status_code=404,detail="Artwork preview unavailable")
    return FileResponse(resolved,media_type="image/png",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"inline"})


@app.get("/commerce/jobs/{job_id}/mockups/{asset_id}")
def commerce_mockup_asset_route(job_id:str,asset_id:str,request:Request):
    _require_read_only_asset(request)
    if not re.fullmatch(r"mockup-[a-f0-9]{12,64}",asset_id):raise HTTPException(status_code=404,detail="Mockup unavailable")
    service=CommerceCreationService()
    try:snapshot=service.review_snapshot(job_id);state=service.orchestrator.load(job_id)
    except (FileNotFoundError,KeyError,ValueError):raise HTTPException(status_code=404,detail="Mockup unavailable")
    if not any(item.get("asset_id")==asset_id for item in snapshot.get("mockups") or []):raise HTTPException(status_code=404,detail="Mockup unavailable")
    root=service.orchestrator._path(job_id).parent.resolve();selected=None
    for item in (state.get("evidence") or {}).get("mockups") or []:
        stored=str(item.get("asset_id") or "");path=Path(str(item.get("local_path") or ""))
        try:resolved=path.resolve(strict=True);digest=str(item.get("sha256") or "") or __import__("hashlib").sha256(resolved.read_bytes()).hexdigest()
        except OSError:continue
        if (stored or f"mockup-{digest[:20]}")==asset_id:selected=(resolved,digest);break
    if selected is None:raise HTTPException(status_code=404,detail="Mockup unavailable")
    resolved,digest=selected
    if root not in resolved.parents or not resolved.is_file():raise HTTPException(status_code=403,detail="Mockup forbidden")
    try:
        with Image.open(resolved) as image:image.verify();fmt=image.format
    except (OSError,ValueError):fmt=None
    media={"PNG":"image/png","JPEG":"image/jpeg"}.get(fmt)
    if not media or __import__("hashlib").sha256(resolved.read_bytes()).hexdigest()!=digest:raise HTTPException(status_code=404,detail="Mockup unavailable")
    return FileResponse(resolved,media_type=media,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"inline"})


@app.get("/commerce/jobs/{job_id}/local-candidates/{asset_id}")
def commerce_local_candidate_asset_route(job_id:str,asset_id:str,request:Request):
    _require_read_only_asset(request)
    if not re.fullmatch(r"candidate-[a-f0-9]{12,64}",asset_id):raise HTTPException(status_code=404,detail="Local candidate unavailable")
    service=CommerceCreationService()
    try:snapshot=service.review_snapshot(job_id);state=service.orchestrator.load(job_id)
    except (FileNotFoundError,KeyError,ValueError):raise HTTPException(status_code=404,detail="Local candidate unavailable")
    if not any(item.get("asset_id")==asset_id for item in snapshot.get("local_candidates") or []):raise HTTPException(status_code=404,detail="Local candidate unavailable")
    root=service.orchestrator._path(job_id).parent.resolve();selected=None
    for revision in (state.get("evidence") or {}).get("local_artwork_revisions") or []:
        for item in revision.get("candidates") or []:
            if item.get("asset_id")==asset_id:selected=item;break
    if selected is None:raise HTTPException(status_code=404,detail="Local candidate unavailable")
    try:resolved=Path(str(selected.get("png_path") or "")).resolve(strict=True)
    except OSError:raise HTTPException(status_code=404,detail="Local candidate unavailable")
    if root not in resolved.parents or not resolved.is_file():raise HTTPException(status_code=403,detail="Local candidate forbidden")
    try:
        with Image.open(resolved) as image:image.verify();valid=image.format=="PNG"
    except (OSError,ValueError):valid=False
    if not valid or __import__("hashlib").sha256(resolved.read_bytes()).hexdigest()!=selected.get("png_sha256"):raise HTTPException(status_code=404,detail="Local candidate unavailable")
    return FileResponse(resolved,media_type="image/png",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"inline"})


@app.post("/commerce/jobs/{job_id}/regenerate-local-artwork")
async def commerce_regenerate_review_artwork_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return CommerceCreationService().regenerate_review_artwork(job_id)
    except JamesOSError as exc:
        handle_error(exc,operation="commerce_creation.regenerate_review_artwork",context={"job_id":job_id});raise HTTPException(status_code=409,detail=exc.user_message) from exc


@app.post("/commerce/jobs/{job_id}/retry-local-artwork")
async def commerce_retry_local_artwork_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return CommerceCreationService().retry_local_artwork(job_id)
    except JamesOSError as exc:
        handle_error(exc,operation="commerce_creation.retry_local_artwork",context={"job_id":job_id});raise HTTPException(status_code=409,detail=exc.user_message) from exc


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


def _application_review_identity(service:CommerceCreationService,job_id:str)->tuple[str,dict[str,Any]]:
    review=service.review_snapshot(job_id);loaded=service.orchestrator.load(job_id)
    state=loaded if isinstance(loaded,dict) else {};destination=state.get("destination") or {};package=review.get("printify_package") or {}
    bound={"job_id":job_id,"revision_number":state.get("revision_number"),"profile_id":state.get("commerce_profile_id"),"destination":destination,
        "printify_product_id":review.get("printify_product_id"),"title":package.get("title"),"description":package.get("description"),"tags":review.get("tags"),
        "price_cents":next((row.get("price") for row in package.get("variants") or [] if isinstance(row,dict) and row.get("is_enabled") is True),None),"enabled_variants":package.get("variant_ids"),
        "colors":package.get("garment_colors"),"sizes":package.get("sizes"),"placement":package.get("print_placement") or "front","selected_artwork":review.get("selected_candidate_id")}
    return sha256(json.dumps(bound,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest(),bound


def _application_publication_confirmation(product_id:str,destination:str)->str:
    return (f"This is an external provider write. The existing Printify draft {product_id} will be published to the configured Etsy destination {destination}. "
        "No customer order will be created. This action will not change the reviewed artwork, listing metadata, variants, price, placement, or destination. Approve and publish now?")


@app.get("/app/commerce/jobs/{job_id}/mockup-intake")
def application_mockup_intake_route(job_id:str,request:Request):
    _require_local(request);return MockupReviewService().public(job_id)


@app.post("/app/commerce/jobs/{job_id}/mockup-intake/refresh")
async def application_mockup_refresh_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return MockupReviewService().refresh(job_id)
    except JamesOSError as exc:raise HTTPException(status_code=409,detail=exc.user_message) from exc


@app.post("/app/commerce/jobs/{job_id}/mockup-intake/approve")
async def application_mockup_approve_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return MockupReviewService().prepare(job_id,values.get("selections") or [],confirmed=values.get("confirmed") is True)
    except JamesOSError as exc:raise HTTPException(status_code=422,detail=exc.user_message) from exc


@app.get("/commerce/jobs/{job_id}/mockup-intake/{asset_id}")
def application_mockup_intake_asset_route(job_id:str,asset_id:str,request:Request):
    _require_read_only_asset(request)
    if not re.fullmatch(r"mockup-[a-f0-9]{20}",asset_id):raise HTTPException(status_code=404,detail="Mockup unavailable")
    try:path=MockupReviewService().asset(job_id,asset_id)
    except (JamesOSError,OSError,ValueError):raise HTTPException(status_code=404,detail="Mockup unavailable")
    return FileResponse(path,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"inline"})


@app.get("/app/commerce/mockup-templates")
def application_mockup_templates_route(request:Request):
    _require_local(request);return MockupTemplateRegistry().list()

@app.post("/app/commerce/mockup-templates")
async def application_mockup_template_ingest_route(request:Request,base_image:UploadFile=File(...),shirt_mask:UploadFile=File(...),template_id:str=Form(...),version:str=Form(...),subject_role:str=Form(...),pose:str=Form(...),garment_color:str=Form(...),garment_style:str=Form(...),print_area:str=Form(...),source:str=Form(...),creator:str=Form(...),license:str=Form(...),created_at:str=Form(...),notes:str=Form(...),production_allowed:bool=Form(False),eligibility_confirmed:bool=Form(False),csrf_token:str=Form(...)):
    _require_local(request);_validate_commerce_origin(request)
    if not hmac.compare_digest(csrf_token,_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:
        role_categories={"clean_product":"product-only","male_model":"male","female_model":"female","lifestyle":"lifestyle"};area=json.loads(print_area)
        metadata={"display_name":template_id.replace("-"," ").title(),"model_category":role_categories.get(subject_role),"subject_role":subject_role,"template_kind":"user_photo","production_allowed":production_allowed,"pose":pose,"garment_color":garment_color,"garment_style":garment_style,"print_area":area,"provenance":{"source":source,"creator":creator,"license":license,"created_at":created_at,"notes":notes}}
        return MockupTemplateIngestService().ingest(template_id=template_id,version=version,base_bytes=await base_image.read(),mask_bytes=await shirt_mask.read(),metadata=metadata,eligibility_confirmed=eligibility_confirmed)
    except (JamesOSError,ValueError) as exc:raise HTTPException(status_code=422,detail=getattr(exc,"user_message","Template metadata is invalid.")) from exc


@app.get("/app/commerce/jobs/{job_id}/mockup-composer")
def application_mockup_composer_route(job_id:str,request:Request):
    _require_local(request);return DeterministicMockupComposer().public(job_id)


@app.post("/app/commerce/jobs/{job_id}/mockup-composer/compose")
async def application_mockup_compose_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return DeterministicMockupComposer().compose(job_id,str(values.get("template_id") or ""),str(values.get("version") or ""),str(values.get("role") or ""))
    except JamesOSError as exc:raise HTTPException(status_code=422,detail=exc.user_message) from exc


@app.post("/app/commerce/jobs/{job_id}/mockup-composer/approve")
async def application_mockup_composer_approve_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    try:return DeterministicMockupComposer().approve(job_id,values.get("ordered_ids") or [],str(values.get("primary_id") or ""),confirmed=values.get("confirmed") is True)
    except JamesOSError as exc:raise HTTPException(status_code=422,detail=exc.user_message) from exc


@app.get("/commerce/jobs/{job_id}/composed-mockups/{asset_id}")
def application_composed_mockup_asset_route(job_id:str,asset_id:str,request:Request):
    _require_read_only_asset(request)
    if not re.fullmatch(r"composed-[a-f0-9]{20}",asset_id):raise HTTPException(status_code=404,detail="Mockup unavailable")
    try:path=DeterministicMockupComposer().asset(job_id,asset_id)
    except (JamesOSError,OSError,ValueError):raise HTTPException(status_code=404,detail="Mockup unavailable")
    return FileResponse(path,media_type="image/png",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff","Content-Disposition":"inline"})


@app.post("/app/commerce/jobs/{job_id}/approve-and-publish")
async def application_approve_and_publish_route(job_id:str,request:Request):
    _require_local(request);_validate_commerce_origin(request);values=await request.json()
    if not hmac.compare_digest(str(values.get("csrf_token") or ""),_COMMERCE_CREATE_CSRF):raise HTTPException(status_code=403,detail="Invalid same-origin token")
    service=CommerceCreationService()
    try:
        identity,bound=_application_review_identity(service,job_id);state=service.orchestrator.load(job_id);destination=state.get("destination") or {}
        if values.get("confirmed") is not True:
            return {"confirmation_required":True,"confirmation":_application_publication_confirmation(str(bound.get("printify_product_id") or ""),str(destination.get("etsy_shop_slug") or "")),
                "review_identity":identity,"revision_number":int(bound.get("revision_number") or 0),"destination":destination.get("etsy_shop_slug"),"publication_performed":False,"order_created":False}
        if not hmac.compare_digest(str(values.get("review_identity") or ""),identity) or int(values.get("revision_number",-1))!=int(bound.get("revision_number") or 0):raise StateConflictError("PUBLICATION_STATE_CONFLICT",diagnostic_message="The reviewed product proposal changed. Reload and review it again.",operation="commerce_publication",stage="proposal",retryable=False)
        if not hmac.compare_digest(str(values.get("destination") or ""),str(destination.get("etsy_shop_slug") or "")):raise StateConflictError("PUBLICATION_PROFILE_CHANGED",diagnostic_message="The configured Etsy destination changed. Publication was blocked.",operation="commerce_publication",stage="profile",retryable=False)
        workflow=CommerceWorkflow(service.orchestrator);status=workflow.status(job_id)
        if not status.get("proposal_exists"):
            service.orchestrator.review_draft(job_id);prepared=workflow.prepare(job_id);proposal_sha=str(prepared["proposal_sha256"])
        else:proposal_sha=str(status.get("proposal_sha256") or "")
        if workflow._state(job_id).get("stage")=="awaiting_final_approval":workflow.approve(job_id,proposal_sha,confirmed=True)
        result=_commerce_publication_executor(workflow,job_id).execute(job_id=job_id,proposal_sha256=proposal_sha,confirmed=True)
        return {**result,"job_id":job_id,"printify_product_id":bound["printify_product_id"],"destination":destination.get("etsy_shop_slug"),"order_state":"not_created"}
    except JamesOSError as exc:
        handle_error(exc,operation="commerce_publication",context={"job_id":job_id});raise HTTPException(status_code=409,detail=exc.user_message) from exc


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
