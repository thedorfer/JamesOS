from __future__ import annotations

from io import StringIO
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout

import requests

from jamesos.core.errors import ERROR_CODES, ArtifactIntegrityError, FontAcquisitionError, ValidationError
from jamesos.core.structured_logging import JsonFormatter, REDACTED, redact
from jamesos.integrations.printify_client import PrintifyAPIError, PrintifyClient
from jamesos.services import error_handler, sale_candidate_vector
from scripts import sale_candidate_run


class ErrorHandlerTests(unittest.TestCase):
    def test_typed_fields_registry_defaults_and_unique_ids(self):
        error = ValidationError("VALIDATION_FAILED", operation="test", stage="input", diagnostic_message="specific")
        self.assertEqual((error.category, error.severity, error.retryable), ("validation", "warning", False))
        self.assertEqual(error.user_message, ERROR_CODES["VALIDATION_FAILED"].user_message)
        self.assertNotEqual(error_handler.new_error_id(), error_handler.new_error_id())

    def test_recursive_redaction_headers_bearer_and_sensitive_url(self):
        value = {"authorization": "Bearer abc", "nested": [{"password": "pw", "url": "https://x.test/a?token=abc&ok=1"}],
                 "headers": {"X": "not persisted"}, "message": "Bearer abc"}
        safe = redact(value)
        self.assertEqual(safe["authorization"], REDACTED); self.assertEqual(safe["nested"][0]["password"], REDACTED)
        self.assertIn("token=%5BREDACTED%5D", safe["nested"][0]["url"]); self.assertNotIn("headers", safe)
        self.assertEqual(safe["message"], REDACTED)

    def test_json_formatter_and_duplicate_propagation_disabled(self):
        stream = StringIO(); handler = logging.StreamHandler(stream); handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("jamesos.test.structured"); logger.handlers = [handler]; logger.propagate = False; logger.setLevel(logging.INFO)
        logger.error("ignored", extra={"structured": {"error_id": "err-test", "authorization": "secret"}})
        parsed = json.loads(stream.getvalue()); self.assertEqual(parsed["error_id"], "err-test"); self.assertEqual(parsed["authorization"], REDACTED)
        self.assertFalse(error_handler.error_logger().propagate)

    def test_diagnostic_atomic_unique_and_persistence_failure_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); exc = ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", operation="test", stage="sha")
            envelope = error_handler.handle_error(exc, operation="test", diagnostic_root=root, log=False)
            path = Path(envelope["diagnostic_artifact_path"]); self.assertTrue(path.is_file())
            before = path.read_bytes()
            with self.assertRaises(FileExistsError): error_handler._persist(envelope, root)
            self.assertEqual(path.read_bytes(), before); self.assertFalse(list(path.parent.glob("*.tmp")))
            blocked = root / "blocked"; blocked.write_text("file")
            safe = error_handler.handle_error(exc, operation="test", diagnostic_root=blocked, log=False)
            self.assertEqual(safe["code"], "ARTIFACT_SHA_MISMATCH"); self.assertIsNone(safe["diagnostic_artifact_path"])

    def test_cause_chain_unexpected_and_boundary_shapes(self):
        cause = ValueError("low-level")
        typed = FontAcquisitionError("FONT_ACQUISITION_INCOMPLETE", operation="fonts", stage="download", cause=cause)
        typed.__cause__ = cause
        envelope = error_handler.handle_error(typed, operation="fonts", persist=False, log=False)
        self.assertEqual(envelope["cause_chain"][1]["type"], "ValueError")
        status, body = error_handler.api_error(envelope); self.assertEqual(status, 422); self.assertNotIn("diagnostic_message", body)
        cli = error_handler.cli_error(envelope); self.assertEqual(cli["result"], "failed"); self.assertIn("error_id", cli)
        unexpected = error_handler.handle_error(RuntimeError("private detail"), operation="test", persist=False, log=False)
        self.assertEqual(unexpected["code"], "UNEXPECTED_INTERNAL_ERROR")
        self.assertNotIn("private detail", error_handler.cli_error(unexpected)["user_message"])

    def test_font_404_is_typed_and_preserves_transaction_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); calls = 0
            def download(_url):
                nonlocal calls; calls += 1
                if calls == 7:
                    response = Mock(status_code=404); exc = requests.HTTPError("not found"); exc.response = response; raise exc
                return Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf").read_bytes() if calls % 2 else b"SIL OPEN FONT LICENSE Version 1.1"
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=Mock(stdout="Coiny Fredoka Lilita One|Regular SemiBold")):
                with self.assertRaises(FontAcquisitionError) as raised:
                    sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "fonts", downloader=download)
            self.assertEqual(raised.exception.code, "FONT_RESOURCE_NOT_FOUND")
            self.assertEqual(raised.exception.state["permanent_files_changed"], False); self.assertTrue(raised.exception.state["staging_cleaned"])

    def test_printify_status_mapping_and_write_has_one_attempt(self):
        unauthorized = PrintifyAPIError("list_shops", 401, "bad_token", "provider detail")
        limited = PrintifyAPIError("list_shops", 429, "limited", "later", True)
        authentication = PrintifyAPIError("authentication", None, "not_configured", "token unavailable")
        upload = PrintifyAPIError("upload_image", 400, "bad_image", "validation failed")
        create = PrintifyAPIError("create_product", 400, "bad_product", "validation failed")
        update = PrintifyAPIError("update_product", 400, "8150", "Validation failed.")
        generic = PrintifyAPIError("get_product", 200, "invalid_json", "Response was not valid JSON.")

        self.assertEqual(unauthorized.code, "HTTP_UNAUTHORIZED"); self.assertNotIn("provider detail", unauthorized.user_message)
        self.assertEqual(limited.code, "HTTP_RATE_LIMITED"); self.assertTrue(limited.retryable)
        self.assertEqual(authentication.code, "PRINTIFY_AUTHENTICATION_FAILED")
        self.assertEqual(upload.code, "PRINTIFY_UPLOAD_FAILED")
        self.assertEqual(create.code, "PRINTIFY_PRODUCT_CREATE_FAILED")
        self.assertEqual(update.code, "PRINTIFY_PRODUCT_UPDATE_FAILED")
        self.assertEqual(update.user_message, "The Printify product draft could not be updated.")
        self.assertNotIn("upload", update.user_message.lower())
        self.assertIn("draft-update payload", update.suggested_action)
        self.assertEqual(generic.code, "PRINTIFY_REQUEST_FAILED")

        with tempfile.TemporaryDirectory() as temporary:
            token = Path(temporary) / "token"; token.write_text("secret"); token.chmod(0o600)
            response = Mock(status_code=500, headers={}); response.json.return_value = {"message": "failed"}
            session = Mock(); session.request.return_value = response
            client = PrintifyClient(token_path=token, session=session)
            with self.assertRaises(PrintifyAPIError): client.create_product(1, {})
            self.assertEqual(session.request.call_count, 1)

            update_response=Mock(status_code=400,headers={});update_response.json.return_value={"status":"error","code":8150,
                "message":"Validation failed.","errors":{"variants":["Invalid variant"],"authorization":"secret","password":"private",
                    "nested":{"access_token":"secret","detail":"Bearer secret"}}}
            session.reset_mock();session.request.return_value=update_response
            with self.assertRaises(PrintifyAPIError) as raised:client.update_product(1,"draft",{})
            self.assertEqual(session.request.call_count,1);self.assertEqual(raised.exception.code,"PRINTIFY_PRODUCT_UPDATE_FAILED")
            envelope=error_handler.handle_error(raised.exception,operation="test",diagnostic_root=Path(temporary)/"diagnostics",log=False)
            provider=envelope["context"]["provider_response"]
            self.assertEqual(provider["provider_status"],"error");self.assertEqual(provider["provider_error_code"],"8150")
            self.assertEqual(provider["provider_errors"]["variants"],["Invalid variant"])
            self.assertEqual(provider["provider_errors"]["authorization"],REDACTED);self.assertEqual(provider["provider_errors"]["password"],REDACTED)
            self.assertEqual(provider["provider_errors"]["nested"]["access_token"],REDACTED);self.assertEqual(provider["provider_errors"]["nested"]["detail"],REDACTED)
            persisted=json.loads(Path(envelope["diagnostic_artifact_path"]).read_text());self.assertEqual(persisted["context"]["provider_response"],provider)
            cli=error_handler.cli_error(envelope);self.assertNotIn("provider",json.dumps(cli).lower());self.assertNotIn("Invalid variant",json.dumps(cli))
            json.dumps(envelope)

    def test_cli_boundary_is_safe_json_and_nonzero(self):
        envelope = error_handler.handle_error(ValidationError("VALIDATION_FAILED", operation="cli", stage="input"),
                                               operation="cli", persist=False, log=False)
        output = StringIO()
        with patch.object(sale_candidate_run, "_main", side_effect=ValidationError("VALIDATION_FAILED", operation="cli", stage="input")), \
             patch.object(sale_candidate_run, "handle_error", return_value=envelope), redirect_stdout(output):
            status = sale_candidate_run.main()
        payload = json.loads(output.getvalue()); self.assertEqual(status, 1); self.assertEqual(payload["result"], "failed")
        self.assertNotIn("diagnostic_message", payload)

    def test_printify_catalog_reads_include_provider_listing_and_out_of_stock_variants(self):
        with tempfile.TemporaryDirectory() as temporary:
            token=Path(temporary)/"token";token.write_text("secret");token.chmod(0o600)
            response=Mock(status_code=200);response.json.return_value={};session=Mock();session.request.return_value=response
            client=PrintifyClient(token_path=token,session=session)
            client.get_blueprint(12);client.list_print_providers_for_blueprint(12);client.get_variants(12,29,show_out_of_stock=True)
            urls=[call.args[1] for call in session.request.call_args_list]
            self.assertTrue(urls[0].endswith("/catalog/blueprints/12.json"))
            self.assertTrue(urls[1].endswith("/catalog/blueprints/12/print_providers.json"))
            self.assertTrue(urls[2].endswith("/catalog/blueprints/12/print_providers/29/variants.json?show-out-of-stock=1"))
            self.assertTrue(all(call.kwargs.get("json") is None for call in session.request.call_args_list))

    def test_printify_gpsr_is_read_only_and_publish_write_has_one_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            token=Path(temporary)/"token";token.write_text("secret");token.chmod(0o600);session=Mock()
            ok=Mock(status_code=200);ok.json.return_value={"sections":[]};session.request.return_value=ok;client=PrintifyClient(token_path=token,session=session)
            client.get_product_gpsr(9437076,"product");call=session.request.call_args
            self.assertEqual(call.args[0],"GET");self.assertTrue(call.args[1].endswith("/shops/9437076/products/product/gpsr.json"))
            failed=Mock(status_code=500,headers={});failed.json.return_value={"message":"failed"};session.reset_mock();session.request.return_value=failed
            with self.assertRaises(PrintifyAPIError):client.publish_product(9437076,"product",{"images":True})
            self.assertEqual(session.request.call_count,1);self.assertEqual(session.request.call_args.args[0],"POST")


if __name__ == "__main__": unittest.main()
