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
from jamesos.services.error_handler import handle_error


ROOT=VAULT/"JamesOS"/"Commerce"/"copilot"/"sessions"
SESSION_RE=re.compile(r"^[A-Za-z0-9_-]{20,100}$")
FIELDS=("exact_phrase","product_brief","listing_title","special_instructions")
SCHEMA={"type":"object","additionalProperties":False,"required":["message","suggestions"],"properties":{
    "message":{"type":"string"},"suggestions":{"type":"object","additionalProperties":False,
        "required":["exact_phrase","product_brief","listing_title","special_instructions","garment_colors","artwork_palette","listing_tags","risk_notes"],
        "properties":{"exact_phrase":{"type":"string"},"product_brief":{"type":"string"},"listing_title":{"type":"string"},"special_instructions":{"type":"string"},
            "garment_colors":{"type":"array","items":{"type":"string"}},"artwork_palette":{"type":"array","items":{"type":"string"}},
            "listing_tags":{"type":"array","items":{"type":"string"}},"risk_notes":{"type":"array","items":{"type":"string"}}}}}}
SCHEMA_TEXT=json.dumps(SCHEMA,separators=(",",":"))


def parse_json_object(raw:Any,max_chars:int=50000)->dict[str,Any]:
    text=str(raw).strip()
    if len(text)>max_chars:raise ValueError("structured response exceeds size limit")
    try:value=json.loads(text)
    except json.JSONDecodeError: value=None
    if isinstance(value,dict):return value
    fenced=re.fullmatch(r"```json\s*(.*?)\s*```",text,re.I|re.S)
    if fenced:
        value=json.loads(fenced.group(1))
        if not isinstance(value,dict):raise ValueError("structured response is not an object")
        return value
    start=text.find("{")
    while start>=0:
        depth=0;quoted=False;escaped=False
        for index in range(start,len(text)):
            char=text[index]
            if quoted:
                if escaped:escaped=False
                elif char=="\\":escaped=True
                elif char=='"':quoted=False
                continue
            if char=='"':quoted=True
            elif char=="{":depth+=1
            elif char=="}":
                depth-=1
                if depth==0:
                    value=json.loads(text[start:index+1])
                    if not isinstance(value,dict):raise ValueError("structured response is not an object")
                    return value
        start=text.find("{",start+1)
    raise ValueError("no complete JSON object found")


def _bounded_string(value:Any,limit:int,field:str)->str:
    if not isinstance(value,str):raise ValueError(f"{field} must be a string")
    clean=" ".join(value.split())
    if len(clean)>limit:raise ValueError(f"{field} exceeds size limit")
    return clean


def validate_contract(value:dict[str,Any])->dict[str,Any]:
    source=value.get("suggestions")
    if source is None:source=value
    if not isinstance(source,dict):raise ValueError("suggestions must be an object")
    result={key:_bounded_string(source.get(key,""),limit,key) for key,limit in (("exact_phrase",500),("product_brief",5000),("listing_title",140),("special_instructions",3000))}
    for key,item_limit,count_limit in (("garment_colors",100,12),("artwork_palette",100,12),("listing_tags",100,30),("risk_notes",500,12)):
        values=source.get(key,[])
        if not isinstance(values,list) or len(values)>count_limit:raise ValueError(f"{key} must be a bounded list")
        clean=[];seen=set()
        for item in values:
            normalized=_bounded_string(item,item_limit,key)
            if not normalized or normalized.casefold() in seen:continue
            seen.add(normalized.casefold());clean.append(normalized)
        result[key]=clean
    return {"message":_bounded_string(value.get("message",value.get("response","")),4000,"message"),"suggestions":result}


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
    def __init__(self,*,model:Callable[[str],str]|None=None,readiness:Callable[[],dict]=ollama_readiness,root:Path=ROOT):self.model=model or ask_ollama;self.structured_model=model is None;self.readiness=readiness;self.root=root

    def _generate(self,prompt:str)->str:
        return self.model(prompt,format_schema=SCHEMA) if self.structured_model else self.model(prompt)

    def _local_fallback(self,context:dict[str,Any])->dict[str,Any]:
        form=context["form"];brand=context.get("brand") or {};niche=" ".join(str(brand.get("niche") or "product").replace("_"," ").split());style=" ".join(str(brand.get("style") or "bold graphic").split())
        phrase=form.get("exact_phrase") or f"{niche} mode".upper()[:500]
        brief=form.get("product_brief") or f"A {style} typography design for the {niche} niche, prepared for human review."
        title=form.get("listing_title") or f"{phrase.title()} Unisex Tee"[:140]
        palette=brand.get("palette") if isinstance(brand.get("palette"),list) else []
        special=form.get("special_instructions") or (f"Use the artwork palette {', '.join(str(x) for x in palette[:8])}. Keep artwork colors separate from garment colors." if palette else "Keep artwork colors separate from garment colors and maintain high contrast.")
        garments=(context.get("garment_defaults") or {}).get("colors") or []
        return {"message":"Local fallback suggestion — the model response could not be structured safely.","suggestions":{"exact_phrase":phrase,"product_brief":brief,
            "listing_title":title,"special_instructions":special,"garment_colors":[str(x) for x in garments[:12]],"artwork_palette":[str(x) for x in palette[:12]],
            "listing_tags":[],"risk_notes":["The local model response was unusable. Review this deterministic fallback before applying it."]}}

    def message(self,*,session_id:str,profile:dict[str,Any],message:str,form:dict[str,Any])->dict[str,Any]:
        if not SESSION_RE.fullmatch(session_id):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio session ID is invalid.",operation="commerce_copilot",stage="input")
        message=" ".join(str(message).split())
        if not message or len(message)>2000:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio message is empty or too long.",operation="commerce_copilot",stage="input")
        context=safe_profile_context(profile,form);path=self.root/f"{session_id}.json"
        history=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"session_id":session_id,"profile_id":context["profile_id"],"messages":[]}
        if history.get("profile_id")!=context["profile_id"]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product Studio session is bound to a different commerce profile.",operation="commerce_copilot",stage="profile")
        prompt=("You are JamesOS Product Studio. Return exactly one JSON object matching the supplied schema. No markdown fences, introductory prose, trailing commentary, JavaScript syntax, or comments. "
            "Garment colors and artwork_palette must remain separate. Give suggestions only; never invoke tools, providers, publication, orders, cancellation, shop changes, or form submission. "
            f"Required schema: {SCHEMA_TEXT}\n"
            f"Safe profile context: {json.dumps(context,ensure_ascii=False)}\nUser request: {message}")
        try:self.readiness()
        except Exception as exc:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Desktop Ollama readiness failed: {type(exc).__name__}: {exc}",
            user_message="Product Studio is temporarily unavailable because the local AI service is not ready.",operation="commerce_copilot",stage="readiness",cause=exc) from exc
        raw="";repair_raw="";parse_error=None;contract=None
        try:
            raw=str(self._generate(prompt));contract=validate_contract(parse_json_object(raw))
        except Exception as exc:
            parse_error=exc;repair_prompt=("Repair the malformed response below into exactly one JSON object matching the required schema. Return corrected JSON only: no markdown, prose, trailing text, JavaScript, or comments. "
                f"Required schema: {SCHEMA_TEXT}\nMalformed response:\n{raw[:50000]}")
            try:repair_raw=str(self._generate(repair_prompt));contract=validate_contract(parse_json_object(repair_raw))
            except Exception as repair_exc:
                parse_error=repair_exc;contract=self._local_fallback(context)
                diagnostic=ValidationError("VALIDATION_FAILED",diagnostic_message=f"Product Studio structured response and one repair attempt failed: {type(repair_exc).__name__}: {repair_exc}",
                    user_message="Product Studio used a safe local fallback because the model response was invalid.",operation="commerce_copilot",stage="structured_response",
                    context={"initial_response":raw[:50000],"repair_response":repair_raw[:50000],"repair_attempts":1},cause=repair_exc)
                handle_error(diagnostic,operation="commerce_copilot",context={"profile_id":context["profile_id"]})
        value=contract;suggestions=dict(value["suggestions"]);garment=suggestions["garment_colors"];artwork=suggestions["artwork_palette"]
        title=suggestions["listing_title"] or context["form"]["listing_title"]
        raw_tags=suggestions.get("listing_tags") or []
        tag_result={"final_listing_tags":[]};tags_valid=False
        if raw_tags or contract.get("message","").startswith("Local fallback"):
            try:tag_result=finalize_listing_tags(raw_tags,profile,title);suggestions["listing_tags"]=tag_result["final_listing_tags"];tags_valid=True
            except ValidationError as exc:
                suggestions.pop("listing_tags",None);suggestions["risk_notes"].append("Thirteen relevant Etsy tags could not be produced safely; tags were omitted for review.")
                tag_result={key:exc.context.get(key,[]) for key in ("raw_generated_tags","normalized_generated_tags","rejected_tags","duplicate_tags","profile_fallback_tags_used","final_listing_tags")}
        else:suggestions.pop("listing_tags",None)
        result={"message":value["message"],"suggestions":suggestions,"tags_valid":tags_valid,"tag_diagnostics":tag_result,
            "used_local_fallback":value["message"].startswith("Local fallback"),"safe_warning":"Product Studio used a safe local fallback because the model response was invalid." if value["message"].startswith("Local fallback") else None,
            "actions":["Apply exact phrase","Apply product brief","Apply listing title","Apply special instructions","Apply all"]}
        history["messages"].append({"created_at":datetime.now().astimezone().isoformat(),"user":message,"response":result["message"],"suggestions":suggestions})
        history["messages"]=history["messages"][-30:];path.parent.mkdir(parents=True,exist_ok=True)
        from jamesos.services.product_orchestrator import _atomic_json
        _atomic_json(path,history)
        return result
