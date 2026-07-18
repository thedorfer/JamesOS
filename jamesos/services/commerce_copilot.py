from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any,Callable

from jamesos.config import VAULT
from jamesos.core.errors import ValidationError
from jamesos.services.ollama_service import ask_ollama,ollama_readiness
from jamesos.services.product_orchestrator import finalize_listing_tags


ROOT=VAULT/"JamesOS"/"Commerce"/"copilot"/"sessions"
SESSION_RE=re.compile(r"^[A-Za-z0-9_-]{20,100}$")
FIELDS=("exact_phrase","product_brief","listing_title","special_instructions")


def safe_profile_context(profile:dict[str,Any],form:dict[str,Any])->dict[str,Any]:
    config=profile.get("configuration") or {}
    return {"profile_id":str(profile.get("profile_id") or ""),"brand_name":str(profile.get("display_name") or config.get("brand_name") or ""),
        "brand":{"niche":config.get("niche") or profile.get("niche"),"voice":config.get("voice") or config.get("brand_voice"),
            "style":config.get("style") or config.get("brand_style"),"palette":config.get("palette") or config.get("artwork_palette")},
        "destination":{"printify_shop_title":config.get("printify_shop_title"),"printify_shop_id":config.get("printify_shop_id"),"etsy_shop_slug":config.get("etsy_shop_slug")},
        "garment_defaults":config.get("garment_defaults") or {"colors":config.get("garment_colors") or config.get("default_colors"),"sizes":config.get("garment_sizes") or config.get("default_sizes")},
        "listing_policy":config.get("listing_policy"),"pricing_policy":config.get("pricing_policy"),
        "form":{key:" ".join(str(form.get(key) or "").split())[:limit] for key,limit in (("exact_phrase",500),("product_brief",5000),("listing_title",140),("special_instructions",3000))}}


class CommerceCopilotService:
    def __init__(self,*,model:Callable[[str],str]=ask_ollama,readiness:Callable[[],dict]=ollama_readiness,root:Path=ROOT):self.model=model;self.readiness=readiness;self.root=root

    def message(self,*,session_id:str,profile:dict[str,Any],message:str,form:dict[str,Any])->dict[str,Any]:
        if not SESSION_RE.fullmatch(session_id):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio session ID is invalid.",operation="commerce_copilot",stage="input")
        message=" ".join(str(message).split())
        if not message or len(message)>2000:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio message is empty or too long.",operation="commerce_copilot",stage="input")
        context=safe_profile_context(profile,form);path=self.root/f"{session_id}.json"
        history=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"session_id":session_id,"profile_id":context["profile_id"],"messages":[]}
        if history.get("profile_id")!=context["profile_id"]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio session is bound to a different commerce profile.",operation="commerce_copilot",stage="profile")
        prompt=("You are JamesOS Product Studio. Return JSON only with keys: message, exact_phrase, product_brief, garment_colors, artwork_palette, listing_title, special_instructions, listing_tags, risk_notes. "
            "Garment colors and artwork_palette must remain separate. Give suggestions only; never invoke tools, providers, publication, orders, shop changes, or form submission. "
            f"Safe profile context: {json.dumps(context,ensure_ascii=False)}\nUser request: {message}")
        try:self.readiness()
        except Exception as exc:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Desktop Ollama readiness failed: {type(exc).__name__}: {exc}",
            user_message="Product Studio is temporarily unavailable because the local AI service is not ready.",operation="commerce_copilot",stage="readiness",cause=exc) from exc
        try:raw=self.model(prompt)
        except Exception as exc:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Desktop Ollama generation failed: {type(exc).__name__}: {exc}",
            user_message="Product Studio could not complete that request. Please try again.",operation="commerce_copilot",stage="generation",cause=exc) from exc
        raw=str(raw).strip()
        if raw.startswith("```"):raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.I)
        try:value=json.loads(raw)
        except (TypeError,json.JSONDecodeError) as exc:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio returned an invalid structured response.",user_message="Product Studio could not complete that request. Please try again.",operation="commerce_copilot",stage="model",cause=exc) from exc
        if not isinstance(value,dict):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio response was not an object.",user_message="Product Studio could not complete that request. Please try again.",operation="commerce_copilot",stage="model")
        suggestions={key:" ".join(str(value.get(key) or "").split())[:limit] for key,limit in (("exact_phrase",500),("product_brief",5000),("listing_title",140),("special_instructions",3000))}
        garment=[" ".join(str(item).split()) for item in value.get("garment_colors") or [] if str(item).strip()][:12]
        artwork=[" ".join(str(item).split()) for item in value.get("artwork_palette") or [] if str(item).strip()][:12]
        title=suggestions["listing_title"] or context["form"]["listing_title"]
        raw_tags=value.get("listing_tags",value.get("tags") or [])
        try:tag_result=finalize_listing_tags(raw_tags,profile,title)
        except ValidationError as exc:tag_result={key:exc.context.get(key,[]) for key in ("raw_generated_tags","normalized_generated_tags","rejected_tags","duplicate_tags","profile_fallback_tags_used","final_listing_tags")}
        suggestions.update({"garment_colors":garment,"artwork_palette":artwork,"listing_tags":tag_result["final_listing_tags"],
            "risk_notes":[" ".join(str(item).split())[:500] for item in value.get("risk_notes",value.get("concerns") or []) if str(item).strip()][:12]})
        result={"message":" ".join(str(value.get("message",value.get("response") or "")).split())[:4000],"suggestions":suggestions,
            "tags_valid":len(tag_result["final_listing_tags"])==13,"tag_diagnostics":tag_result,
            "actions":["Apply exact phrase","Apply product brief","Apply listing title","Apply special instructions","Apply all"]}
        history["messages"].append({"created_at":datetime.now().astimezone().isoformat(),"user":message,"response":result["message"],"suggestions":suggestions})
        history["messages"]=history["messages"][-30:];path.parent.mkdir(parents=True,exist_ok=True)
        from jamesos.services.product_orchestrator import _atomic_json
        _atomic_json(path,history)
        return result
