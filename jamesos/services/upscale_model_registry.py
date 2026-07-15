from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from jamesos.services.job_queue import JobQueueError


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "upscale_models.yaml"
COMFYUI_ROOT = Path.home() / "AI" / "ComfyUI"
MODEL_EXTENSIONS = {".pth", ".pt", ".safetensors", ".ckpt"}


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_upscale_model_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    registry_path = path or REGISTRY_PATH
    try:
        loaded = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise JobQueueError(f"Upscale model registry could not be read: {exc}") from exc
    models = loaded.get("models") or {}
    if not isinstance(models, dict):
        raise JobQueueError("Upscale model registry must contain a models mapping.")
    return {str(name): dict(metadata or {}) for name, metadata in models.items()}


def _path_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def configured_upscale_model_roots(comfyui_root: Path | None = None) -> list[Path]:
    root = (comfyui_root or COMFYUI_ROOT).expanduser()
    roots = [root / "models" / "upscale_models"]
    extra_config = root / "extra_model_paths.yaml"
    if extra_config.exists():
        try:
            loaded = yaml.safe_load(extra_config.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise JobQueueError(f"ComfyUI extra model paths could not be read: {exc}") from exc
        for section in loaded.values() if isinstance(loaded, dict) else []:
            if not isinstance(section, dict):
                continue
            base_path = Path(str(section.get("base_path") or root)).expanduser()
            if not base_path.is_absolute():
                base_path = root / base_path
            for configured in _path_values(section.get("upscale_models")):
                candidate = Path(configured).expanduser()
                roots.append(candidate if candidate.is_absolute() else base_path / candidate)
    unique: list[Path] = []
    for candidate in roots:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def discover_upscale_models(model_roots: list[Path] | None = None) -> list[dict[str, Any]]:
    roots = model_roots or configured_upscale_model_roots()
    discovered: dict[str, dict[str, Any]] = {}
    for root in roots:
        expanded = Path(root).expanduser()
        if not expanded.exists():
            continue
        for path in sorted(expanded.rglob("*"), key=lambda item: str(item).lower()):
            if not path.is_file() or path.suffix.lower() not in MODEL_EXTENSIONS:
                continue
            model_name = path.relative_to(expanded).as_posix()
            discovered.setdefault(model_name, {
                "model_name": model_name,
                "file_path": str(path.resolve()),
                "exists": True,
                "file_size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            })
    return sorted(discovered.values(), key=lambda item: item["model_name"].lower())


def list_upscale_models(
    *,
    registry_path: Path | None = None,
    model_roots: list[Path] | None = None,
) -> dict[str, Any]:
    configured = load_upscale_model_config(registry_path)
    installed = discover_upscale_models(model_roots)
    installed_by_name = {item["model_name"]: item for item in installed}
    models: list[dict[str, Any]] = []
    for name, config in configured.items():
        discovered = installed_by_name.get(name, {})
        configured_validated = bool(config.get("validated", False))
        validated_model_sha256 = str(config.get("validated_model_sha256") or "")
        installed_sha256 = str(discovered.get("sha256", ""))
        if not configured_validated:
            effective_validated = False
            validation_reason = "not_validated"
        elif not validated_model_sha256:
            effective_validated = False
            validation_reason = "validated_hash_missing"
        elif not discovered.get("exists", False):
            effective_validated = False
            validation_reason = "model_missing"
        elif installed_sha256 != validated_model_sha256:
            effective_validated = False
            validation_reason = "model_hash_mismatch"
        else:
            effective_validated = True
            validation_reason = "model_hash_match"
        models.append({
            "model_name": str(config.get("model_name") or name),
            "file_path": discovered.get("file_path", ""),
            "exists": bool(discovered.get("exists", False)),
            "file_size_bytes": int(discovered.get("file_size_bytes", 0)),
            "sha256": str(discovered.get("sha256", "")),
            "scale_factor": config.get("scale_factor"),
            "model_family": str(config.get("model_family") or "unknown"),
            "intended_use": str(config.get("intended_use") or "manual review"),
            "enabled": bool(config.get("enabled", False)),
            "validated": effective_validated,
            "configured_validated": configured_validated,
            "production_approved": effective_validated,
            "validation_reason": validation_reason,
            "validated_model_sha256": validated_model_sha256,
            "validation_job_id": str(config.get("validation_job_id") or ""),
            "validation_output_sha256": str(config.get("validation_output_sha256") or ""),
            "validated_at": str(config.get("validated_at") or ""),
            "preferred_alpha_resize_method": str(config.get("preferred_alpha_resize_method") or "lanczos"),
            "preferred_edge_bleed_iterations": config.get("preferred_edge_bleed_iterations", 16),
            "preferred_edge_bleed_alpha_threshold": config.get("preferred_edge_bleed_alpha_threshold", 128),
            "default": bool(config.get("default", False)),
            "validation_output_filename": str(config.get("validation_output_filename") or "upscale-model-validation.png"),
            "configured": True,
        })
    configured_names = set(configured)
    for discovered in installed:
        if discovered["model_name"] in configured_names:
            continue
        models.append({
            **discovered,
            "scale_factor": None,
            "model_family": "unknown",
            "intended_use": "unconfigured; manual review required",
            "enabled": False,
            "validated": False,
            "configured_validated": False,
            "production_approved": False,
            "validation_reason": "not_configured",
            "validated_model_sha256": "",
            "validation_job_id": "",
            "validation_output_sha256": "",
            "validated_at": "",
            "preferred_alpha_resize_method": "lanczos",
            "preferred_edge_bleed_iterations": 16,
            "preferred_edge_bleed_alpha_threshold": 128,
            "default": False,
            "validation_output_filename": "upscale-model-validation.png",
            "configured": False,
        })
    defaults = [item for item in models if item["configured"] and item["default"]]
    default_model = defaults[0]["model_name"] if len(defaults) == 1 else ""
    return {
        "status": "ok",
        "installed_models": installed,
        "configured_models": [item for item in models if item["configured"]],
        "models": sorted(models, key=lambda item: item["model_name"].lower()),
        "default_model": default_model,
        "validation_state": {
            "configured_count": len(configured),
            "installed_count": len(installed),
            "enabled_installed_count": len([item for item in models if item["enabled"] and item["exists"]]),
            "validated_count": len([item for item in models if item["validated"]]),
        },
    }


def select_upscale_model(
    model_name: str | None = None,
    *,
    registry_path: Path | None = None,
    model_roots: list[Path] | None = None,
) -> dict[str, Any]:
    inventory = list_upscale_models(registry_path=registry_path, model_roots=model_roots)
    selected_name = str(model_name or inventory["default_model"] or "").strip()
    pure_name = PurePosixPath(selected_name.replace("\\", "/"))
    if not selected_name or pure_name.is_absolute() or ".." in pure_name.parts:
        raise JobQueueError("Upscale model selection must be a configured model name, not a filesystem path.")
    selected = next((item for item in inventory["models"] if item["model_name"] == selected_name), None)
    if selected is None:
        raise JobQueueError(f"Unknown upscale model: {selected_name}")
    if not selected["configured"]:
        raise JobQueueError(f"Upscale model is installed but not configured: {selected_name}")
    if not selected["enabled"]:
        raise JobQueueError(f"Upscale model is disabled: {selected_name}")
    if not selected["exists"]:
        raise JobQueueError(f"Configured upscale model is missing: {selected_name}")
    scale_factor = selected.get("scale_factor")
    if not isinstance(scale_factor, int) or isinstance(scale_factor, bool) or scale_factor not in {2, 4}:
        raise JobQueueError(f"Upscale model has an invalid configured scale factor: {selected_name}")
    return selected
