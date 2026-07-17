from __future__ import annotations

from datetime import datetime
from typing import Any

from jamesos.core.agent_manager.compatibility import compatibility

from .manifest import AgencyManifest, AgencyManifestError, validate_field
from .registry import CatalogProvider
from .storage import AgencyStore


class AgencyError(ValueError):
    def __init__(self, message: str, *, code: str = "AGENCY_ERROR"):
        super().__init__(message)
        self.code = code


class AgencyService:
    def __init__(self, catalog: CatalogProvider, store: AgencyStore, secrets):
        self.catalog = catalog
        self.store = store
        self.secrets = secrets

    def catalog_items(self) -> list[dict[str, Any]]:
        installed = self.store.load()["agents"]
        return [self._view(item, installed.get(item.package.agent_id)) for item in self.catalog.list_manifests()]

    def team(self) -> list[dict[str, Any]]:
        state = self.store.load()["agents"]
        return [self._view(self._manifest(agent_id), record) for agent_id, record in sorted(state.items())]

    def details(self, agent_id: str) -> dict[str, Any]:
        return self._view(self._manifest(agent_id), self.store.load()["agents"].get(agent_id), details=True)

    def hire(self, agent_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        manifest = self._manifest(agent_id)
        if compatibility(manifest.package) != "compatible":
            raise AgencyError("agent is incompatible with this JamesOS version", code="INCOMPATIBLE")
        state = self.store.load()
        if agent_id in state["agents"]:
            raise AgencyError("agent is already hired", code="DUPLICATE_HIRE")
        if not confirmed:
            return {"action": "hire", "agent_id": agent_id, "confirmation_required": True, "changed": False}
        now = _now()
        defaults = {field["name"]: field["default"] for field in manifest.configuration if "default" in field}
        state["agents"][agent_id] = {
            "version": manifest.package.version,
            "enabled": False,
            "configuration": defaults,
            "permission_grants": {},
            "secret_grants": {},
            "hired_at": now,
            "updated_at": now,
            "activity": [{"event": "hired", "timestamp": now}],
        }
        self.store.save(state)
        return {"action": "hire", "agent_id": agent_id, "confirmation_required": False, "changed": True}

    def release(self, agent_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        state = self.store.load()
        self._record(state, agent_id)
        if not confirmed:
            return {"action": "release", "agent_id": agent_id, "confirmation_required": True, "changed": False}
        del state["agents"][agent_id]
        self.store.save(state)
        return {"action": "release", "agent_id": agent_id, "changed": True}

    def set_enabled(self, agent_id: str, enabled: bool, *, confirmed: bool = False) -> dict[str, Any]:
        state = self.store.load()
        record = self._record(state, agent_id)
        manifest = self._manifest(agent_id)
        missing = self._missing(manifest, record)
        if enabled and any(missing.values()):
            raise AgencyError(f"agent setup is incomplete: {', '.join(key for key, value in missing.items() if value)}", code="NOT_READY")
        action = "enable" if enabled else "disable"
        if not confirmed:
            return {"action": action, "agent_id": agent_id, "confirmation_required": True, "changed": False}
        record["enabled"] = enabled
        self._activity(record, "enabled" if enabled else "disabled")
        self.store.save(state)
        return {"action": action, "agent_id": agent_id, "changed": True}

    def configuration(self, agent_id: str) -> dict[str, Any]:
        manifest, record = self._installed(agent_id)
        return {"schema": list(manifest.configuration), "values": dict(record["configuration"])}

    def update_configuration(self, agent_id: str, values: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
        manifest, record = self._installed(agent_id)
        fields = {field["name"]: field for field in manifest.configuration}
        unknown = set(values) - set(fields)
        if unknown:
            raise AgencyError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
        validated = {name: validate_field(fields[name], value) for name, value in values.items()}
        if not confirmed:
            return {"action": "configure", "confirmation_required": True, "changed": False}
        state = self.store.load()
        record = self._record(state, agent_id)
        record["configuration"].update(validated)
        self._activity(record, "configuration_updated")
        self.store.save(state)
        return self.configuration(agent_id)

    def permissions(self, agent_id: str) -> dict[str, Any]:
        manifest, record = self._installed(agent_id)
        return {"required": manifest.permissions_required, "optional": manifest.permissions_optional, "granted": record["permission_grants"]}

    def update_permissions(self, agent_id: str, grants: dict[str, list[str]], *, confirmed: bool = False) -> dict[str, Any]:
        manifest, _ = self._installed(agent_id)
        requested = {key: set(values) for key, values in manifest.permissions_required.items()}
        for key, values in manifest.permissions_optional.items():
            requested.setdefault(key, set()).update(values)
        for key, values in grants.items():
            if key not in requested or not set(values) <= requested[key]:
                raise AgencyError("permission grant was not requested")
        if not confirmed:
            return {"action": "permissions", "confirmation_required": True, "changed": False}
        state = self.store.load()
        record = self._record(state, agent_id)
        record["permission_grants"] = {key: list(values) for key, values in grants.items()}
        self._activity(record, "permissions_updated")
        self.store.save(state)
        return self.permissions(agent_id)

    def secret_status(self, agent_id: str) -> dict[str, Any]:
        manifest, record = self._installed(agent_id)
        requirements = []
        for requirement in manifest.secrets:
            handle = record["secret_grants"].get(requirement["name"])
            requirements.append({
                "name": requirement["name"],
                "required": bool(requirement.get("required", False)),
                "handle": handle,
                "configured": bool(handle and self.secrets.status(handle)["configured"]),
            })
        return {"requirements": requirements}

    def update_secrets(self, agent_id: str, grants: dict[str, str | None], *, confirmed: bool = False) -> dict[str, Any]:
        manifest, _ = self._installed(agent_id)
        names = {item["name"] for item in manifest.secrets}
        if not set(grants) <= names:
            raise AgencyError("unknown secret requirement")
        for handle in grants.values():
            if handle is not None and not self.secrets.status(handle)["configured"]:
                raise AgencyError("secret handle is unavailable")
        if not confirmed:
            return {"action": "secret_grants", "confirmation_required": True, "changed": False}
        state = self.store.load()
        record = self._record(state, agent_id)
        for name, handle in grants.items():
            if handle is None:
                record["secret_grants"].pop(name, None)
            else:
                record["secret_grants"][name] = handle
        self._activity(record, "secret_grants_updated")
        self.store.save(state)
        return self.secret_status(agent_id)

    def activity(self, agent_id: str) -> dict[str, Any]:
        _, record = self._installed(agent_id)
        return {"activity": list(record["activity"])}

    def create_secret(self, label: str, value: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            return {"action": "create_secret", "confirmation_required": True, "changed": False}
        return self.secrets.create(label, value)

    def _manifest(self, agent_id: str) -> AgencyManifest:
        try:
            return next(item for item in self.catalog.list_manifests() if item.package.agent_id == agent_id)
        except StopIteration as exc:
            raise AgencyError("agent not found", code="NOT_FOUND") from exc

    def _record(self, state: dict[str, Any], agent_id: str) -> dict[str, Any]:
        try:
            return state["agents"][agent_id]
        except KeyError as exc:
            raise AgencyError("agent is not hired", code="NOT_HIRED") from exc

    def _installed(self, agent_id: str):
        state = self.store.load()
        return self._manifest(agent_id), self._record(state, agent_id)

    def _missing(self, manifest: AgencyManifest, record: dict[str, Any]) -> dict[str, list[str]]:
        configuration = [field["name"] for field in manifest.configuration if field.get("required") and field["name"] not in record["configuration"]]
        permissions = []
        for category, required in manifest.permissions_required.items():
            if not set(required) <= set(record["permission_grants"].get(category, ())):
                permissions.extend(f"{category}:{item}" for item in set(required) - set(record["permission_grants"].get(category, ())))
        secrets = []
        for requirement in manifest.secrets:
            handle = record["secret_grants"].get(requirement["name"])
            if requirement.get("required") and not (handle and self.secrets.status(handle)["configured"]):
                secrets.append(requirement["name"])
        return {"configuration": configuration, "permissions": permissions, "secrets": secrets}

    def _view(self, manifest: AgencyManifest, record: dict[str, Any] | None, *, details: bool = False) -> dict[str, Any]:
        result = manifest.public_dict()
        result["installed"] = record is not None
        result["status"] = "active" if record and record["enabled"] else ("off_duty" if record else "available")
        if record:
            missing = self._missing(manifest, record)
            if any(missing.values()):
                result["status"] = "degraded"
            result.update({"installed_version": record["version"], "missing": missing, "update_available": False})
        if not details:
            result.pop("configuration", None)
            result.pop("secrets", None)
        return result

    @staticmethod
    def _activity(record: dict[str, Any], event: str) -> None:
        timestamp = _now()
        record["updated_at"] = timestamp
        record["activity"].append({"event": event, "timestamp": timestamp})


def _now() -> str:
    return datetime.now().astimezone().isoformat()
