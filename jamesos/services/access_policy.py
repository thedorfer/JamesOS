from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
from typing import Mapping, Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from jamesos.config import JAMESOS_DATA


RUNTIME_ENV = JAMESOS_DATA / "JamesOS" / "runtime.env"
MODES = {"loopback", "tailnet", "lan"}
TAILSCALE_IDENTITY_HEADERS = {
    "tailscale-user-login", "tailscale-user-name", "tailscale-user-profile-pic",
}


def _runtime_values(path: Path = RUNTIME_ENV) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"JAMESOS_ACCESS_MODE", "JAMESOS_TRUSTED_HOSTS", "JAMESOS_TRUSTED_ORIGINS", "JAMESOS_ALLOWED_NETWORKS"}:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _items(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in value.replace(";", ",").split(",") if item.strip()))


def _host(value: str) -> str:
    if not value or "," in value or "@" in value:
        raise ValueError("invalid host")
    parsed = urlsplit(f"//{value}")
    if parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment or not parsed.hostname:
        raise ValueError("invalid host")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid port")
    return value.casefold()


def _origin(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("invalid origin")
    hostname = parsed.hostname.casefold()
    authority = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        authority += f":{parsed.port}"
    return f"{parsed.scheme}://{authority}", authority


@dataclass(frozen=True)
class AccessPolicy:
    mode: str = "loopback"
    trusted_hosts: tuple[str, ...] = ()
    trusted_origins: tuple[str, ...] = ()
    allowed_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()
    configuration_error: str | None = None

    @classmethod
    def from_values(cls, values: Mapping[str, str] | None = None) -> "AccessPolicy":
        values = dict(values or {})
        mode = values.get("JAMESOS_ACCESS_MODE", "loopback").strip().casefold() or "loopback"
        errors: list[str] = []
        if mode not in MODES:
            errors.append("unsupported access mode")
        hosts: list[str] = []
        for item in _items(values.get("JAMESOS_TRUSTED_HOSTS", "")):
            try: hosts.append(_host(item))
            except ValueError: errors.append("invalid trusted host")
        origins: list[str] = []
        for item in _items(values.get("JAMESOS_TRUSTED_ORIGINS", "")):
            try:
                normalized, _ = _origin(item)
                if mode == "tailnet" and not normalized.startswith("https://"):
                    errors.append("Tailnet origins must use HTTPS")
                origins.append(normalized)
            except ValueError: errors.append("invalid trusted origin")
        networks = []
        for item in _items(values.get("JAMESOS_ALLOWED_NETWORKS", "")):
            try: networks.append(ipaddress.ip_network(item, strict=True))
            except ValueError: errors.append("invalid allowed network")
        if mode in {"tailnet", "lan"} and (not hosts or not origins):
            errors.append("trusted hosts and origins are required")
        if mode == "lan" and not networks:
            errors.append("explicit LAN networks are required")
        return cls(mode=mode if mode in MODES else "loopback", trusted_hosts=tuple(hosts), trusted_origins=tuple(origins),
            allowed_networks=tuple(networks), configuration_error="; ".join(dict.fromkeys(errors)) or None)

    @classmethod
    def from_runtime_env(cls, path: Path = RUNTIME_ENV) -> "AccessPolicy":
        return cls.from_values(_runtime_values(path))

    @property
    def bind_host(self) -> str:
        return "0.0.0.0" if self.mode == "lan" and not self.configuration_error else "127.0.0.1"

    def _client(self, request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        raw = request.client.host if request.client else ""
        # Starlette's in-process TestClient uses a non-socket sentinel. A real
        # network connection always supplies an IP address in the ASGI scope.
        if raw == "testclient":
            return ipaddress.ip_address("127.0.0.1")
        try: return ipaddress.ip_address(raw)
        except ValueError as exc: raise HTTPException(status_code=403, detail="Client network is not allowed") from exc

    @staticmethod
    def _single_header(request: Request, name: str, *, required: bool = True) -> str | None:
        getlist = getattr(request.headers, "getlist", None)
        values = list(getlist(name)) if callable(getlist) else ([request.headers.get(name)] if request.headers.get(name) is not None else [])
        if (required and len(values) != 1) or len(values) > 1:
            raise HTTPException(status_code=403, detail=f"Invalid {name}")
        return values[0].strip() if values else None

    def authorize(self, request: Request, *, require_origin: bool = False, validate_client: bool = True) -> None:
        if self.configuration_error:
            raise HTTPException(status_code=503, detail="JamesOS access configuration is unsafe")
        client = self._client(request) if validate_client else None
        if validate_client:
            if self.mode in {"loopback", "tailnet"} and not client.is_loopback:
                raise HTTPException(status_code=403, detail="Client network is not allowed")
            if self.mode == "lan" and not any(client in network for network in self.allowed_networks):
                raise HTTPException(status_code=403, detail="Client network is not allowed")

        if not hasattr(request, "headers"):
            return
        if validate_client and any(request.headers.get(name) is not None for name in TAILSCALE_IDENTITY_HEADERS) and not client.is_loopback:
            raise HTTPException(status_code=403, detail="Untrusted proxy identity headers")

        host = self._single_header(request, "host")
        try: normalized_host = _host(host or "")
        except ValueError as exc: raise HTTPException(status_code=400, detail="Invalid host header") from exc
        if self.mode == "loopback":
            host_name = urlsplit(f"//{normalized_host}").hostname
            request_client = getattr(request, "client", None)
            test_client = request_client is not None and request_client.host == "testclient"
            if host_name not in {"localhost", "127.0.0.1", "::1"} and not (test_client and host_name == "testserver"):
                raise HTTPException(status_code=400, detail="Invalid host header")
        elif normalized_host not in self.trusted_hosts:
            raise HTTPException(status_code=400, detail="Invalid host header")

        origin = self._single_header(request, "origin", required=require_origin)
        if origin is None:
            return
        try: normalized_origin, origin_host = _origin(origin)
        except ValueError as exc: raise HTTPException(status_code=403, detail="Invalid origin") from exc
        if self.mode == "loopback":
            parsed = urlsplit(normalized_origin)
            if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or origin_host != normalized_host:
                raise HTTPException(status_code=403, detail="Invalid origin")
        elif normalized_origin not in self.trusted_origins or origin_host != normalized_host:
            raise HTTPException(status_code=403, detail="Invalid origin")

    def status(self, request: Request) -> dict[str, Any]:
        client = self._client(request)
        host = request.headers.get("host", "unknown").split(",", 1)[0]
        forwarded_https = self.mode == "tailnet" and client.is_loopback and request.headers.get("x-forwarded-proto", "").casefold() == "https"
        https = request.url.scheme == "https" or forwarded_https
        proxy_type = "Tailscale Serve loopback proxy" if self.mode == "tailnet" else ("direct LAN client" if self.mode == "lan" else "local loopback client")
        return {"access_mode": self.mode, "trusted_hostname": host, "https": https, "connection_type": proxy_type,
            "access_scope": "Tailnet" if self.mode == "tailnet" else ("LAN" if self.mode == "lan" else "local"),
            "warning": "LAN access is using plain HTTP; use HTTPS when possible." if self.mode == "lan" and not https else None}
