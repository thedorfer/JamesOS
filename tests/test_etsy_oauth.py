from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs,urlsplit

from jamesos.integrations import etsy_oauth
from jamesos.integrations.etsy_client import EtsyClient,EtsyShopResponseError,normalize_owner_shop_response


class EtsyOAuthAuthorizationTests(unittest.TestCase):
    def fixture(self,root:Path):
        app=root/"app.json";pending=root/"pending.json";token=root/"token.json"
        app.write_text(json.dumps({"keystring":"public-client-id","shared_secret":"private","redirect_uri":"https://example.test/exact/callback"}));app.chmod(0o600)
        token.write_text(json.dumps({"access_token":"private","refresh_token":"private","scopes":["listings_r","listings_w"]}));token.chmod(0o600)
        return app,pending,token

    def test_authorization_url_has_exact_allowlisted_parameters_and_scopes(self):
        with TemporaryDirectory() as temporary:
            app,pending,token=self.fixture(Path(temporary));result=etsy_oauth.start(app,pending,token,now=100)
            parsed=urlsplit(result["authorization_url"]);query=parse_qs(parsed.query)
            self.assertEqual(set(query),set(etsy_oauth.AUTHORIZATION_PARAMETER_NAMES))
            self.assertFalse(set(query)&{"resource","audience","target","resource_uri","resource_server"})
            self.assertEqual(query["redirect_uri"],["https://example.test/exact/callback"]);self.assertEqual(query["response_type"],["code"])
            self.assertEqual(set(query["scope"][0].split()),{"listings_r","listings_w","shops_r"})
            self.assertEqual(query["code_challenge_method"],["S256"]);self.assertTrue(query["state"][0]);self.assertTrue(query["code_challenge"][0])

    def test_failed_callback_invalidates_evidence_and_does_not_update_token(self):
        with TemporaryDirectory() as temporary:
            app,pending,token=self.fixture(Path(temporary));before=token.read_bytes();started=etsy_oauth.start(app,pending,token,now=100)
            state=parse_qs(urlsplit(started["authorization_url"]).query)["state"][0]
            callback=f"https://example.test/exact/callback?error=invalid_target&error_description=safe&state={state}"
            with self.assertRaisesRegex(ValueError,"authorization failed"):etsy_oauth.complete(callback,app,pending,token,now=101)
            self.assertFalse(pending.exists());self.assertEqual(token.read_bytes(),before)
            with self.assertRaises(Exception):etsy_oauth.complete(callback,app,pending,token,now=102)

    def test_fresh_attempt_uses_new_state_verifier_and_challenge(self):
        with TemporaryDirectory() as temporary:
            app,pending,token=self.fixture(Path(temporary));first=etsy_oauth.start(app,pending,token,now=100);private_first=json.loads(pending.read_text())
            state=parse_qs(urlsplit(first["authorization_url"]).query)["state"][0]
            with self.assertRaises(ValueError):etsy_oauth.complete(f"https://example.test/exact/callback?error=invalid_target&state={state}",app,pending,token,now=101)
            second=etsy_oauth.start(app,pending,token,now=102);private_second=json.loads(pending.read_text())
            q1=parse_qs(urlsplit(first["authorization_url"]).query);q2=parse_qs(urlsplit(second["authorization_url"]).query)
            self.assertNotEqual(q1["state"],q2["state"]);self.assertNotEqual(q1["code_challenge"],q2["code_challenge"]);self.assertNotEqual(private_first["verifier"],private_second["verifier"])
            self.assertEqual(pending.stat().st_mode&0o777,0o600)

    def test_documented_single_shop_object_is_primary_response(self):
        value={"shop_id":123456,"user_id":69293108,"shop_name":"UnityStitches","url":"https://ignored.example"}
        self.assertEqual(normalize_owner_shop_response(value,69293108),{"shop_id":123456,"user_id":69293108,"shop_name":"UnityStitches","status":None})

    def test_owner_shop_requires_exact_fields_and_owner(self):
        invalid=({"user_id":69293108,"shop_name":"UnityStitches"},{"shop_id":1,"user_id":69293108,"shop_name":""},
            {"shop_id":1,"user_id":99,"shop_name":"UnityStitches"},{"count":1})
        expected=("ETSY_SHOP_RESPONSE_INVALID","ETSY_SHOP_RESPONSE_INVALID","ETSY_SHOP_OWNERSHIP_MISMATCH","ETSY_SHOP_RESPONSE_INVALID")
        for value,code in zip(invalid,expected):
            with self.subTest(code=code),self.assertRaises(EtsyShopResponseError) as raised:normalize_owner_shop_response(value,69293108)
            self.assertEqual(raised.exception.code,code)

    def test_client_owner_shop_lookup_is_one_get_and_has_no_write_surface(self):
        class Response:
            status_code=200
            def json(self):return {"shop_id":7,"user_id":69293108,"shop_name":"Exact"}
        class Session:
            def __init__(self):self.calls=[]
            def request(self,method,url,**kwargs):self.calls.append((method,url));return Response()
        session=Session();client=EtsyClient({"keystring":"k","shared_secret":"s","access_token":"t"},session=session)
        self.assertEqual(client.get_shop_by_owner_user_id(69293108)["shop_id"],7);self.assertEqual(len(session.calls),1);self.assertEqual(session.calls[0][0],"GET")
        self.assertNotIn("UnityStitches",session.calls[0][1]);self.assertFalse(hasattr(client,"create_order"));self.assertFalse(hasattr(client,"publish_product"))


if __name__=="__main__":unittest.main()
