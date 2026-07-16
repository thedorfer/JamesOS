from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import requests

from jamesos.config import VAULT
from jamesos.core.errors import PrintifyError
from jamesos.core.structured_logging import redact


BASE_URL = "https://api.printify.com/v1"
TOKEN_PATH = VAULT / "JamesOS" / "Secrets" / "printify_api_token.txt"
USER_AGENT = "JamesOS/1.0 PrintifyDraftIntegration"

_OPERATION_ERROR_CODES = {
    "authentication": "PRINTIFY_AUTHENTICATION_FAILED",
    "upload_image": "PRINTIFY_UPLOAD_FAILED",
    "create_product": "PRINTIFY_PRODUCT_CREATE_FAILED",
    "update_product": "PRINTIFY_PRODUCT_UPDATE_FAILED",
}

_OPERATION_SUGGESTED_ACTIONS = {
    "authentication": "Verify the Printify token exists, is nonempty, and has safe file permissions.",
    "upload_image": "Review the artwork file and upload request, then retry only after correcting the reported condition.",
    "create_product": "Review the product-draft payload and Printify validation details before creating another draft.",
    "update_product": "Review the Printify validation details and correct the draft-update payload before retrying.",
}


def _bounded_provider_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8: return "[TRUNCATED]"
    if isinstance(value, dict):
        items=list(value.items()); result={str(key):_bounded_provider_value(item,depth=depth+1) for key,item in items[:100]}
        if len(items)>100: result["__truncated_items__"]=len(items)-100
        return result
    if isinstance(value, list):
        result=[_bounded_provider_value(item,depth=depth+1) for item in value[:100]]
        if len(value)>100: result.append(f"[TRUNCATED {len(value)-100} ITEMS]")
        return result
    if isinstance(value, str): return value[:4000]
    if value is None or isinstance(value,(bool,int,float)): return value
    return str(value)[:1000]


def _provider_response(value: dict[str, Any] | None) -> dict[str, Any]:
    return _bounded_provider_value(redact(value or {}))


class PrintifyAPIError(PrintifyError):
    def __init__(self, operation: str, http_status: int | None, error_code: str, safe_message: str, retryable: bool = False,
                 provider_response: dict[str, Any] | None = None) -> None:
        code = ({401: "HTTP_UNAUTHORIZED", 403: "HTTP_FORBIDDEN", 404: "HTTP_NOT_FOUND", 429: "HTTP_RATE_LIMITED"}.get(http_status)
                or ("HTTP_SERVER_ERROR" if http_status is not None and http_status >= 500 else
                    _OPERATION_ERROR_CODES.get(operation, "PRINTIFY_REQUEST_FAILED")))
        self.http_status, self.error_code, self.safe_message = http_status, error_code, safe_message
        protected_response=_provider_response(provider_response or {"provider_status":http_status,"provider_error_code":error_code,
            "provider_message":safe_message,"provider_errors":None})
        super().__init__(code, diagnostic_message=f"Printify {operation} failed ({http_status or 'network'}, {error_code}): {safe_message}",
            operation=f"printify.{operation}", stage="http_request", retryable=retryable,
            context={"http_status": http_status, "provider_error_code": error_code,"provider_response":protected_response},
            suggested_action=_OPERATION_SUGGESTED_ACTIONS.get(
                operation,
                "Review the Printify response and use the error ID to inspect the protected diagnostic record.",
            ))


def token_status(path: Path = TOKEN_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "not_configured", "token_path": str(path), "permissions_valid": False}
    mode = path.stat().st_mode & 0o777
    return {"status": "configured" if mode & 0o077 == 0 else "invalid_permissions",
            "token_path": str(path), "permissions_valid": mode & 0o077 == 0}


class PrintifyClient:
    def __init__(self, *, token_path: Path = TOKEN_PATH, session: requests.Session | None = None,
                 base_url: str = BASE_URL, timeout: tuple[float, float] = (10.0, 45.0)) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Printify API base URL must use HTTPS.")
        self.token_path, self.session, self.base_url, self.timeout = token_path, session or requests.Session(), base_url.rstrip("/"), timeout

    def _token(self) -> str:
        status = token_status(self.token_path)
        if status["status"] != "configured":
            raise PrintifyAPIError("authentication", None, status["status"], "Printify token is unavailable or has unsafe permissions.")
        token = self.token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise PrintifyAPIError("authentication", None, "empty_token", "Printify token file is empty.")
        return token

    def _request(self, method: str, path: str, *, operation: str, payload: dict[str, Any] | None = None,
                 safe_read: bool = False) -> Any:
        headers = {"Authorization": f"Bearer {self._token()}", "User-Agent": USER_AGENT,
                   "Content-Type": "application/json;charset=utf-8", "Accept": "application/json"}
        attempts = 3 if safe_read else 1
        for attempt in range(attempts):
            try:
                response = self.session.request(method, f"{self.base_url}{path}", headers=headers,
                                                json=payload, timeout=self.timeout)
            except requests.RequestException as exc:
                if safe_read and attempt + 1 < attempts:
                    continue
                raise PrintifyAPIError(operation, None, "network_error", type(exc).__name__, safe_read) from exc
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError as exc:
                    raise PrintifyAPIError(operation, response.status_code, "invalid_json", "Response was not valid JSON.") from exc
            retryable = response.status_code == 429 or response.status_code >= 500
            if safe_read and retryable and attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After", "0")
                try: time.sleep(min(float(retry_after), 2.0))
                except ValueError: pass
                continue
            try: body = response.json()
            except ValueError: body = {}
            token = headers["Authorization"].removeprefix("Bearer ")
            code = str(body.get("code") or body.get("error") or f"http_{response.status_code}").replace(token, "[REDACTED]")[:100]
            message = str(body.get("message") or body.get("error_description") or "Printify rejected the request.").replace(token, "[REDACTED]")[:500]
            provider_response={"provider_status":body.get("status",response.status_code),"provider_error_code":code,
                "provider_message":message,"provider_errors":body.get("errors")}
            provider_response=json.loads(json.dumps(provider_response,default=str).replace(token,"[REDACTED]"))
            raise PrintifyAPIError(operation, response.status_code, code, message, retryable,provider_response)
        raise AssertionError("unreachable")

    def list_shops(self): return self._request("GET", "/shops.json", operation="list_shops", safe_read=True)
    def list_blueprints(self): return self._request("GET", "/catalog/blueprints.json", operation="list_blueprints", safe_read=True)
    def get_blueprint(self, blueprint_id: int): return self._request("GET", f"/catalog/blueprints/{blueprint_id}.json", operation="get_blueprint", safe_read=True)
    def list_print_providers(self): return self._request("GET", "/catalog/print_providers.json", operation="list_print_providers", safe_read=True)
    def list_print_providers_for_blueprint(self, blueprint_id: int): return self._request("GET", f"/catalog/blueprints/{blueprint_id}/print_providers.json", operation="list_blueprint_providers", safe_read=True)
    def get_variants(self, blueprint_id: int, provider_id: int): return self._request("GET", f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json", operation="get_variants", safe_read=True)
    def get_shipping(self, blueprint_id: int, provider_id: int): return self._request("GET", f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/shipping.json", operation="get_shipping", safe_read=True)
    def list_uploads(self): return self._request("GET", "/uploads.json", operation="list_uploads", safe_read=True)
    def get_upload(self, image_id: str): return self._request("GET", f"/uploads/{image_id}.json", operation="get_upload", safe_read=True)
    def upload_image_contents(self, file_name: str, contents: str): return self._request("POST", "/uploads/images.json", operation="upload_image", payload={"file_name": file_name, "contents": contents})
    def upload_image_url(self, file_name: str, url: str):
        if not url.startswith("https://"): raise ValueError("Printify image URL must use HTTPS.")
        return self._request("POST", "/uploads/images.json", operation="upload_image", payload={"file_name": file_name, "url": url})
    def list_products(self, shop_id: int): return self._request("GET", f"/shops/{shop_id}/products.json", operation="list_products", safe_read=True)
    def get_product(self, shop_id: int, product_id: str): return self._request("GET", f"/shops/{shop_id}/products/{product_id}.json", operation="get_product", safe_read=True)
    def create_product(self, shop_id: int, payload: dict[str, Any]): return self._request("POST", f"/shops/{shop_id}/products.json", operation="create_product", payload=payload)
    def update_product(self, shop_id: int, product_id: str, payload: dict[str, Any]): return self._request("PUT", f"/shops/{shop_id}/products/{product_id}.json", operation="update_product", payload=payload)
