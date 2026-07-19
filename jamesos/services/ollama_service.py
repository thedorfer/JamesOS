import json
import urllib.request
from datetime import datetime
from jamesos.config.loader import get_config


FAST_MODEL = "qwen2.5:3b"
DEFAULT_MODEL = "llama3.1:8b"
_READINESS={"reachable":None,"model_installed":None,"model":"","timestamp":None}
_LAST_GENERATION={"endpoint_mode":"generate","http_status":None,"schema_supplied":False,"top_level_keys":[],"shape":"not_requested","text_length":0,"exception_type":None,"failure_stage":"none","timestamp":None}


def _extract_text(data: object) -> tuple[str,str]:
    if not isinstance(data,dict):return "","unsupported_json"
    message=data.get("message")
    if isinstance(message,dict) and isinstance(message.get("content"),str):return message["content"].strip(),"message.content"
    if isinstance(data.get("response"),str):return data["response"].strip(),"response"
    if isinstance(data.get("content"),str):return data["content"].strip(),"content"
    return "","unrecognized"


def chat_diagnostics() -> dict:
    generation=dict(_LAST_GENERATION);readiness=dict(_READINESS)
    return {"readiness":readiness,"generation":generation,"reachable":readiness["reachable"],"model":readiness["model"],**generation}


def ollama_enabled() -> bool:
    return bool(get_config("ollama.yaml").get("ollama", {}).get("enabled", False))


def _model_for_prompt(prompt: str, configured_model: str) -> str:
    lower = prompt.lower()
    if "jade context package: chat" in lower:
        return FAST_MODEL
    if "keep it short" in lower and any(word in lower for word in ["funny", "interesting", "casual", "banter", "conversational"]):
        return FAST_MODEL
    return configured_model or DEFAULT_MODEL


def ask_ollama(prompt: str, model: str | None = None, *, format_schema: dict | str | None = None) -> str:
    cfg = get_config("ollama.yaml").get("ollama", {})
    host = cfg.get("host", "http://127.0.0.1:11434").rstrip("/")
    configured_model = model or cfg.get("model", DEFAULT_MODEL)
    selected_model = _model_for_prompt(prompt, configured_model)
    timeout = int(cfg.get("timeout_seconds", 60))
    endpoint_mode=str(cfg.get("endpoint_mode") or cfg.get("api_mode") or "generate").lower()
    if endpoint_mode not in {"generate","chat"}:endpoint_mode="generate"

    payload={"model":selected_model,"stream":False,"options":{"num_predict":180 if selected_model==FAST_MODEL else 700}}
    if endpoint_mode=="chat":payload["messages"]=[{"role":"user","content":prompt}]
    else:payload["prompt"]=prompt
    if format_schema is not None:payload["format"]=format_schema

    req = urllib.request.Request(
        f"{host}/api/{endpoint_mode}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    _LAST_GENERATION.update(endpoint_mode=endpoint_mode,http_status=None,schema_supplied=format_schema is not None,top_level_keys=[],shape="unrecognized",text_length=0,exception_type=None,failure_stage="connectivity",timestamp=datetime.now().astimezone().isoformat())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status=getattr(resp,"status",200);data=json.loads(resp.read().decode("utf-8"))
        keys=sorted(str(key)[:80] for key in data) if isinstance(data,dict) else [];_LAST_GENERATION.update(http_status=status,top_level_keys=keys,failure_stage="none")
        if isinstance(data,dict) and data.get("error"):raise RuntimeError("Ollama returned an error envelope.")
        text,shape=_extract_text(data);_LAST_GENERATION.update(http_status=status,top_level_keys=keys,shape=shape,text_length=len(text),failure_stage="none" if text else "response_shape")
        if not text:raise RuntimeError("Ollama returned no supported assistant text field.")
        return text
    except Exception as exc:
        _LAST_GENERATION["exception_type"]=type(exc).__name__
        if _LAST_GENERATION["failure_stage"]=="connectivity":_LAST_GENERATION["failure_stage"]="connectivity_or_model"
        elif _LAST_GENERATION["failure_stage"]=="none":_LAST_GENERATION["failure_stage"]="response_error"
        raise


def ollama_readiness() -> dict:
    """Verify the desktop-configured Ollama endpoint and model without generating."""
    cfg=get_config("ollama.yaml").get("ollama",{});host=cfg.get("host","http://127.0.0.1:11434").rstrip("/");model=cfg.get("model",DEFAULT_MODEL)
    try:
        with urllib.request.urlopen(f"{host}/api/tags",timeout=min(5,int(cfg.get("timeout_seconds",60)))) as resp:
            status=getattr(resp,"status",200);data=json.loads(resp.read().decode("utf-8"))
    except Exception:
        _READINESS.update(reachable=False,model_installed=None,model=model,timestamp=datetime.now().astimezone().isoformat())
        raise
    models={str(item.get("name") or "") for item in data.get("models") or []}
    if model not in models:
        _READINESS.update(reachable=True,model_installed=False,model=model,timestamp=datetime.now().astimezone().isoformat());raise RuntimeError(f"Configured Ollama model is unavailable: {model}")
    _READINESS.update(reachable=True,model_installed=True,model=model,timestamp=datetime.now().astimezone().isoformat())
    return {"ready":True,"model":model,"endpoint":host}


def ollama_status() -> str:
    cfg = get_config("ollama.yaml").get("ollama", {})
    host = cfg.get("host", "http://127.0.0.1:11434").rstrip("/")

    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", [])]
        return "Ollama available. Models: " + ", ".join(models)
    except Exception as exc:
        return f"Ollama unavailable: {exc}"
