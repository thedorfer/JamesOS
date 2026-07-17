from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from jamesos.config import VAULT

from .registry import DirectoryCatalogProvider
from .secrets import AgencySecretProvider
from .service import AgencyError, AgencyService
from .storage import AgencyStore


class Confirmation(BaseModel):
    confirmed: bool = False


class ConfigurationUpdate(Confirmation):
    values: dict[str, Any] = Field(default_factory=dict)


class PermissionUpdate(Confirmation):
    grants: dict[str, list[str]] = Field(default_factory=dict)


class SecretGrantUpdate(Confirmation):
    grants: dict[str, str | None] = Field(default_factory=dict)


class SecretCreate(Confirmation):
    label: str
    value: str


def default_service() -> AgencyService:
    catalog = Path(__file__).resolve().parents[3] / "agency" / "manifests"
    root = VAULT / "JamesOS" / "Agency"
    secrets = VAULT / "JamesOS" / "Secrets" / "Agency"
    return AgencyService(DirectoryCatalogProvider(catalog), AgencyStore(root / "state.json"), AgencySecretProvider(secrets))


def _require_key(x_jamesos_key: str | None = Header(default=None)) -> None:
    path = VAULT / "JamesOS" / "Secrets" / "api_key.txt"
    if not path.exists():
        raise HTTPException(status_code=500, detail="API key is not configured")
    if x_jamesos_key != path.read_text(encoding="utf-8").strip():
        raise HTTPException(status_code=401, detail="Unauthorized")


def create_router(service: AgencyService | None = None, *, authenticate: bool = True) -> APIRouter:
    dependencies = [Depends(_require_key)] if authenticate else []
    router = APIRouter(prefix="/agency", tags=["agency"], dependencies=dependencies)
    agency = service or default_service()

    def call(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except AgencyError as exc:
            status = 404 if exc.code in {"NOT_FOUND", "NOT_HIRED"} else 409
            raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.get("/catalog")
    def catalog(): return call(agency.catalog_items)

    @router.post("/secrets")
    def create_secret(body: SecretCreate): return call(agency.create_secret, body.label, body.value, confirmed=body.confirmed)

    @router.get("/agents")
    def agents(): return call(agency.team)

    @router.get("/agents/{agent_id}")
    def details(agent_id: str): return call(agency.details, agent_id)

    @router.post("/agents/{agent_id}/hire")
    def hire(agent_id: str, body: Confirmation): return call(agency.hire, agent_id, confirmed=body.confirmed)

    @router.post("/agents/{agent_id}/release")
    def release(agent_id: str, body: Confirmation): return call(agency.release, agent_id, confirmed=body.confirmed)

    @router.post("/agents/{agent_id}/enable")
    def enable(agent_id: str, body: Confirmation): return call(agency.set_enabled, agent_id, True, confirmed=body.confirmed)

    @router.post("/agents/{agent_id}/disable")
    def disable(agent_id: str, body: Confirmation): return call(agency.set_enabled, agent_id, False, confirmed=body.confirmed)

    @router.get("/agents/{agent_id}/configuration")
    def configuration(agent_id: str): return call(agency.configuration, agent_id)

    @router.put("/agents/{agent_id}/configuration")
    def configure(agent_id: str, body: ConfigurationUpdate): return call(agency.update_configuration, agent_id, body.values, confirmed=body.confirmed)

    @router.get("/agents/{agent_id}/permissions")
    def permissions(agent_id: str): return call(agency.permissions, agent_id)

    @router.put("/agents/{agent_id}/permissions")
    def permission_update(agent_id: str, body: PermissionUpdate): return call(agency.update_permissions, agent_id, body.grants, confirmed=body.confirmed)

    @router.get("/agents/{agent_id}/secrets")
    def secrets(agent_id: str): return call(agency.secret_status, agent_id)

    @router.put("/agents/{agent_id}/secrets")
    def secret_update(agent_id: str, body: SecretGrantUpdate): return call(agency.update_secrets, agent_id, body.grants, confirmed=body.confirmed)

    @router.get("/agents/{agent_id}/activity")
    def activity(agent_id: str): return call(agency.activity, agent_id)

    return router


router = create_router()
