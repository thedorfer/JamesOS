from __future__ import annotations
from dataclasses import asdict, dataclass, field
import re
from typing import Any

SCHEMA_VERSION = "1"
PROTOCOL_VERSION = "1.0.0"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CAPABILITY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
ENTRY_POINT = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$")

class ManifestValidationError(ValueError):pass

@dataclass(frozen=True)
class PackageManifest:
    schema_version:str;protocol_version:str;agent_id:str;name:str;version:str;publisher:str;description:str
    capabilities:tuple[str,...];accepted_task_types:tuple[str,...];emitted_result_types:tuple[str,...]
    required_tool_permissions:tuple[str,...]=();required_secret_handles:tuple[str,...]=();supported_side_effects:tuple[str,...]=()
    protected_resources:tuple[str,...]=();maximum_automatic_attempts:int=1;idempotency_behavior:str="stable_key";execution_mode:str="in_process"
    minimum_jamesos_version:str="0.1.0";maximum_jamesos_version:str|None=None;package_name:str="";entry_point:str="";owner:str=""
    declared_permissions:dict[str,tuple[str,...]]=field(default_factory=dict)
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,value:dict[str,Any]):
        data=dict(value)
        tuple_fields=("capabilities","accepted_task_types","emitted_result_types","required_tool_permissions","required_secret_handles","supported_side_effects","protected_resources")
        for key in tuple_fields:data[key]=tuple(data.get(key) or ())
        data["declared_permissions"]={str(k):tuple(v or ()) for k,v in (data.get("declared_permissions") or {}).items()}
        manifest=cls(**data);validate_manifest(manifest);return manifest

def _version(value,name):
    if not isinstance(value,str) or not SEMVER.fullmatch(value):raise ManifestValidationError(f"{name} must be a semantic version")

def validate_manifest(manifest:PackageManifest)->PackageManifest:
    if manifest.schema_version!=SCHEMA_VERSION:raise ManifestValidationError("unsupported manifest schema")
    _version(manifest.protocol_version,"protocol_version");_version(manifest.version,"version");_version(manifest.minimum_jamesos_version,"minimum_jamesos_version")
    if manifest.maximum_jamesos_version:_version(manifest.maximum_jamesos_version,"maximum_jamesos_version")
    if manifest.protocol_version.split(".")[0]!=PROTOCOL_VERSION.split(".")[0]:raise ManifestValidationError("incompatible protocol version")
    if not manifest.publisher or not manifest.owner:raise ManifestValidationError("publisher and ownership information are required")
    if not manifest.agent_id or not manifest.package_name:raise ManifestValidationError("agent_id and package_name are required")
    if not manifest.entry_point or not ENTRY_POINT.fullmatch(manifest.entry_point) or ".." in manifest.entry_point or manifest.entry_point.startswith("."):raise ManifestValidationError("invalid entry point")
    if not manifest.capabilities or any(not CAPABILITY.fullmatch(item) for item in manifest.capabilities):raise ManifestValidationError("malformed capability")
    declared_side_effects=set(manifest.declared_permissions.get("side_effects",()))
    if not set(manifest.supported_side_effects)<=declared_side_effects:raise ManifestValidationError("undeclared side effect")
    if manifest.maximum_automatic_attempts<1:raise ManifestValidationError("maximum attempts must be positive")
    return manifest
