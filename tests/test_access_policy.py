from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from jamesos.core import api
from jamesos.services.access_policy import AccessPolicy


def request(client: str, host: str, *, origin: str | None = None, scheme: str = "http", extra: list[tuple[bytes, bytes]] | None = None) -> Request:
    headers = [(b"host", host.encode())]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    headers.extend(extra or [])
    return Request({"type": "http", "method": "GET", "path": "/app", "scheme": scheme,
        "server": ("127.0.0.1", 8787), "client": (client, 12345), "headers": headers})


class AccessPolicyTests(unittest.TestCase):
    def test_loopback_is_default_and_remote_clients_origins_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            policy = AccessPolicy.from_runtime_env(Path(temporary) / "missing.env")
        self.assertEqual(policy.mode, "loopback"); self.assertEqual(policy.bind_host, "127.0.0.1")
        policy.authorize(request("127.0.0.1", "127.0.0.1:8787", origin="http://127.0.0.1:8787"), require_origin=True)
        for candidate in (request("192.0.2.8", "127.0.0.1:8787"), request("127.0.0.1", "127.0.0.1:8787", origin="https://host.example")):
            with self.assertRaises(HTTPException): policy.authorize(candidate, require_origin=candidate.headers.get("origin") is not None)

    def test_runtime_env_supports_only_bounded_access_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.env"
            path.write_text("JAMESOS_ACCESS_MODE=tailnet\nJAMESOS_TRUSTED_HOSTS=james.tailnet.ts.net\nJAMESOS_TRUSTED_ORIGINS=https://james.tailnet.ts.net\nSECRET=do-not-read\n")
            policy = AccessPolicy.from_runtime_env(path)
        self.assertEqual(policy.mode, "tailnet"); self.assertIsNone(policy.configuration_error)
        self.assertFalse(hasattr(policy, "SECRET"))

    def test_configured_tailnet_https_origin_succeeds_and_unknown_fails(self):
        policy = AccessPolicy.from_values({"JAMESOS_ACCESS_MODE": "tailnet", "JAMESOS_TRUSTED_HOSTS": "james.tailnet.ts.net",
            "JAMESOS_TRUSTED_ORIGINS": "https://james.tailnet.ts.net"})
        policy.authorize(request("127.0.0.1", "james.tailnet.ts.net", origin="https://james.tailnet.ts.net", extra=[(b"tailscale-user-login", b"user@example.test")]), require_origin=True)
        with self.assertRaises(HTTPException):
            policy.authorize(request("127.0.0.1", "james.tailnet.ts.net", origin="https://unknown.tailnet.ts.net"), require_origin=True)

    def test_spoofed_tailnet_identity_from_non_loopback_fails(self):
        policy = AccessPolicy.from_values({"JAMESOS_ACCESS_MODE": "lan", "JAMESOS_TRUSTED_HOSTS": "james.lan:8787",
            "JAMESOS_TRUSTED_ORIGINS": "http://james.lan:8787", "JAMESOS_ALLOWED_NETWORKS": "192.168.50.0/24"})
        with self.assertRaises(HTTPException):
            policy.authorize(request("192.168.50.4", "james.lan:8787", extra=[(b"tailscale-user-login", b"spoofed")]))

    def test_host_header_attacks_fail(self):
        policies = [AccessPolicy(), AccessPolicy.from_values({"JAMESOS_ACCESS_MODE": "tailnet", "JAMESOS_TRUSTED_HOSTS": "james.tailnet.ts.net", "JAMESOS_TRUSTED_ORIGINS": "https://james.tailnet.ts.net"})]
        for policy in policies:
            with self.subTest(mode=policy.mode), self.assertRaises(HTTPException):
                policy.authorize(request("127.0.0.1", "evil.example"))
        response=TestClient(api.app,base_url="http://127.0.0.1:8787",client=("127.0.0.1",1234)).get("/app",headers={"Host":"evil.example"})
        self.assertEqual(response.status_code,400)

    def test_lan_fails_closed_and_only_explicit_cidr_succeeds(self):
        unsafe = AccessPolicy.from_values({"JAMESOS_ACCESS_MODE": "lan"})
        self.assertIsNotNone(unsafe.configuration_error); self.assertEqual(unsafe.bind_host, "127.0.0.1")
        with self.assertRaises(HTTPException): unsafe.authorize(request("192.168.50.4", "james.lan:8787"))
        policy = AccessPolicy.from_values({"JAMESOS_ACCESS_MODE": "lan", "JAMESOS_TRUSTED_HOSTS": "james.lan:8787",
            "JAMESOS_TRUSTED_ORIGINS": "http://james.lan:8787", "JAMESOS_ALLOWED_NETWORKS": "192.168.50.0/24"})
        policy.authorize(request("192.168.50.9", "james.lan:8787", origin="http://james.lan:8787"), require_origin=True)
        with self.assertRaises(HTTPException): policy.authorize(request("192.168.51.9", "james.lan:8787"))
        self.assertEqual(policy.bind_host, "0.0.0.0"); self.assertIn("plain HTTP", policy.status(request("192.168.50.9", "james.lan:8787"))["warning"])

    def test_access_status_is_sanitized_and_visible_in_admin(self):
        rows=[{"profile_id":"bagholder-supply","display_name":"Bagholder Supply Co.","configuration":{"printify_shop_id":1,"printify_shop_title":"Bagholder","etsy_shop_slug":"bagholder"}}]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=admin.home").text
        for expected in ("Private-network access","Access mode:","Trusted hostname:","HTTPS state:","Direct client/proxy type:","/app/access-status"):
            self.assertIn(expected,text)
        self.assertNotIn("JAMESOS_TRUSTED_ORIGINS",text)

    def test_csrf_and_provider_confirmation_gates_are_unchanged(self):
        service=Mock();provider=Mock(side_effect=AssertionError("provider must not be called"))
        policy=AccessPolicy()
        with patch.object(api.AccessPolicy,"from_runtime_env",return_value=policy),patch.object(api,"WorkspaceChatService",return_value=service):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787",client=("127.0.0.1",1234)).post("/app/chat",json={"csrf_token":"wrong"},headers={"Origin":"http://127.0.0.1:8787"})
        self.assertEqual(response.status_code,403);provider.assert_not_called();service.message.assert_not_called()

    def test_read_only_assets_allow_browser_gets_but_reject_cross_site_headers(self):
        policy=AccessPolicy()
        policy.authorize_read_only_asset(request("127.0.0.1","127.0.0.1:8787"))
        policy.authorize_read_only_asset(request("127.0.0.1","127.0.0.1:8787",origin="http://127.0.0.1:8787"))
        policy.authorize_read_only_asset(request("127.0.0.1","127.0.0.1:8787",extra=[(b"referer",b"http://127.0.0.1:8787/app?view=commerce.review")]))
        for candidate in (
            request("127.0.0.1","127.0.0.1:8787",origin="https://evil.example"),
            request("127.0.0.1","127.0.0.1:8787",extra=[(b"referer",b"https://evil.example/review")]),
            request("127.0.0.1","evil.example"),
        ):
            with self.assertRaises(HTTPException):policy.authorize_read_only_asset(candidate)


if __name__ == "__main__": unittest.main()
