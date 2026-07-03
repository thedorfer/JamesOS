import json
import urllib.request
from jamesos.config.loader import get_config


FAST_MODEL = "qwen2.5:3b"
DEFAULT_MODEL = "llama3.1:8b"


def ollama_enabled() -> bool:
    return bool(get_config("ollama.yaml").get("ollama", {}).get("enabled", False))


def _model_for_prompt(prompt: str, configured_model: str) -> str:
    lower = prompt.lower()
    if "jade context package: chat" in lower:
        return FAST_MODEL
    if "keep it short" in lower and any(word in lower for word in ["funny", "interesting", "casual", "banter", "conversational"]):
        return FAST_MODEL
    return configured_model or DEFAULT_MODEL


def ask_ollama(prompt: str, model: str | None = None) -> str:
    cfg = get_config("ollama.yaml").get("ollama", {})
    host = cfg.get("host", "http://localhost:11434").rstrip("/")
    configured_model = model or cfg.get("model", DEFAULT_MODEL)
    selected_model = _model_for_prompt(prompt, configured_model)
    timeout = int(cfg.get("timeout_seconds", 60))

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 180 if selected_model == FAST_MODEL else 700,
        },
    }

    req = urllib.request.Request(
        f"{host}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return data.get("response", "").strip()


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
