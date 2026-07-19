import json
import urllib.request
from datetime import datetime
from jamesos.config.loader import get_config


FAST_MODEL = "qwen2.5:3b"
DEFAULT_MODEL = "llama3.1:8b"
_LAST_DIAGNOSTIC={"reachable":None,"model":"","endpoint_mode":"generate","http_status":None,"shape":"not_requested","failure_stage":"none","updated_at":None}


def _extract_text(data: object) -> tuple[str,str]:
    if not isinstance(data,dict):return "","unsupported_json"
    message=data.get("message")
    if isinstance(message,dict) and isinstance(message.get("content"),str):return message["content"].strip(),"message.content"
    if isinstance(data.get("response"),str):return data["response"].strip(),"response"
    if isinstance(data.get("content"),str):return data["content"].strip(),"content"
    return "","unrecognized"


def chat_diagnostics() -> dict:
    return dict(_LAST_DIAGNOSTIC)


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
    host = cfg.get("host", "http://localhost:11434").rstrip("/")
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

    _LAST_DIAGNOSTIC.update(reachable=False,model=selected_model,endpoint_mode=endpoint_mode,http_status=None,shape="unrecognized",failure_stage="connectivity",updated_at=datetime.now().astimezone().isoformat())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status=getattr(resp,"status",200);data=json.loads(resp.read().decode("utf-8"))
        text,shape=_extract_text(data);_LAST_DIAGNOSTIC.update(reachable=True,http_status=status,shape=shape,failure_stage="none" if text else "response_shape")
        if not text:raise RuntimeError("Ollama returned no supported assistant text field.")
        return text
    except Exception as exc:
        if _LAST_DIAGNOSTIC["failure_stage"]=="connectivity":_LAST_DIAGNOSTIC["failure_stage"]="connectivity_or_model"
        raise


def ollama_readiness() -> dict:
    """Verify the desktop-configured Ollama endpoint and model without generating."""
    cfg=get_config("ollama.yaml").get("ollama",{});host=cfg.get("host","http://localhost:11434").rstrip("/");model=cfg.get("model",DEFAULT_MODEL)
    with urllib.request.urlopen(f"{host}/api/tags",timeout=min(5,int(cfg.get("timeout_seconds",60)))) as resp:
        data=json.loads(resp.read().decode("utf-8"))
    models={str(item.get("name") or "") for item in data.get("models") or []}
    if model not in models:raise RuntimeError(f"Configured Ollama model is unavailable: {model}")
    return {"ready":True,"model":model,"endpoint":host}


def ollama_status() -> str:
    cfg = get_config("ollama.yaml").get("ollama", {})
    host = cfg.get("host", "http://localhost:11434").rstrip("/")

    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", [])]
        return "Ollama available. Models: " + ", ".join(models)
    except Exception as exc:
        return f"Ollama unavailable: {exc}"
