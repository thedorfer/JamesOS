import json
import urllib.request
from jamesos.config.loader import get_config


def ollama_enabled() -> bool:
    return bool(get_config("ollama.yaml").get("ollama", {}).get("enabled", False))


def ask_ollama(prompt: str) -> str:
    cfg = get_config("ollama.yaml").get("ollama", {})
    host = cfg.get("host", "http://localhost:11434").rstrip("/")
    model = cfg.get("model", "llama3.1:8b")
    timeout = int(cfg.get("timeout_seconds", 60))

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
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
