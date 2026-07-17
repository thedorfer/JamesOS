from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from jamesos.core.agent_manager.manifest import PackageManifest


class AgencyManifestError(ValueError):
    pass


FIELD_TYPES = {"string", "integer", "boolean", "enum", "url"}


@dataclass(frozen=True)
class AgencyManifest:
    package: PackageManifest
    category: str
    tags: tuple[str, ...]
    permissions_required: dict[str, tuple[str, ...]]
    permissions_optional: dict[str, tuple[str, ...]]
    configuration: tuple[dict[str, Any], ...]
    secrets: tuple[dict[str, Any], ...]
    platforms: tuple[dict[str, Any], ...]
    install: dict[str, Any]
    media: dict[str, Any]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgencyManifest":
        try:
            package_data = dict(value["agent"])
            package_data["declared_permissions"] = {
                key: tuple(items)
                for key, items in (value.get("permissions", {}).get("required", {}) or {}).items()
            }
            package = PackageManifest.from_dict(package_data)
        except (KeyError, TypeError, ValueError) as exc:
            raise AgencyManifestError(f"invalid agent metadata: {exc}") from exc
        category = value.get("category")
        if not isinstance(category, str) or not category.strip():
            raise AgencyManifestError("category is required")
        required = _permission_map(value.get("permissions", {}).get("required", {}), "required")
        optional = _permission_map(value.get("permissions", {}).get("optional", {}), "optional")
        fields = tuple(value.get("configuration") or ())
        seen: set[str] = set()
        for field in fields:
            name = field.get("name")
            kind = field.get("type")
            if not isinstance(name, str) or not name or name in seen:
                raise AgencyManifestError("configuration field names must be unique and non-empty")
            if kind not in FIELD_TYPES:
                raise AgencyManifestError(f"configuration field {name} has unsupported type {kind}")
            if kind == "enum" and not field.get("choices"):
                raise AgencyManifestError(f"configuration field {name} requires choices")
            seen.add(name)
            if "default" in field:
                validate_field(field, field["default"])
        secrets = tuple(value.get("secrets") or ())
        secret_names: set[str] = set()
        for requirement in secrets:
            name = requirement.get("name")
            if not isinstance(name, str) or not name or name in secret_names:
                raise AgencyManifestError("secret requirement names must be unique and non-empty")
            if "value" in requirement:
                raise AgencyManifestError("secret requirements may contain references, never values")
            secret_names.add(name)
        return cls(
            package=package,
            category=category.strip(),
            tags=tuple(str(tag) for tag in value.get("tags") or ()),
            permissions_required=required,
            permissions_optional=optional,
            configuration=fields,
            secrets=secrets,
            platforms=tuple(value.get("platforms") or ()),
            install=dict(value.get("install") or {}),
            media=dict(value.get("media") or {}),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.package.schema_version,
            "agent": self.package.to_dict(),
            "category": self.category,
            "tags": list(self.tags),
            "permissions": {
                "required": {key: list(items) for key, items in self.permissions_required.items()},
                "optional": {key: list(items) for key, items in self.permissions_optional.items()},
            },
            "configuration": list(self.configuration),
            "secrets": list(self.secrets),
            "platforms": list(self.platforms),
            "install": self.install,
            "media": self.media,
        }


def _permission_map(value: Any, label: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise AgencyManifestError(f"{label} permissions must be an object")
    return {str(key): tuple(str(item) for item in items) for key, items in value.items()}


def validate_field(field: dict[str, Any], value: Any) -> Any:
    name, kind = field["name"], field["type"]
    valid = (
        (kind == "string" and isinstance(value, str))
        or (kind == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (kind == "boolean" and isinstance(value, bool))
        or (kind == "enum" and value in field.get("choices", ()))
        or (kind == "url" and isinstance(value, str) and urlparse(value).scheme in {"http", "https"})
    )
    if not valid:
        raise AgencyManifestError(f"invalid value for configuration field {name}")
    return value
