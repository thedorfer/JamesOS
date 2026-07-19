import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock,patch

from jamesos.services import ollama_service
from jamesos.services.application_shell import OLLAMA_RESPONSE_SCHEMA,WorkspaceChatService,application_shell_diagnostics


PROFILE={"profile_id":"p","display_name":"P","configuration":{"printify_shop_id":1,"etsy_shop_slug":"P"}}


class OllamaServiceTests(unittest.TestCase):
    def service(self,value):
        model=Mock(return_value=value);temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        result=WorkspaceChatService(model=model,readiness=lambda:{},root=Path(temporary.name)).message(conversation_id="schema-conversation-123456",message="hello",profile=PROFILE,profiles=[PROFILE],workspace={"active_view":"dashboard","form":{}})
        self.assertEqual(model.call_args.kwargs["format_schema"],OLLAMA_RESPONSE_SCHEMA);return result

    def test_schema_envelope_and_plain_conversation_are_both_usable(self):
        structured=self.service(json.dumps({"message":"JADE-OK","commands":[],"suggestions":[],"warnings":[]}));self.assertEqual(structured["message"],"JADE-OK");self.assertEqual(structured["commands"],[]);self.assertEqual(structured["warnings"],[])
        for raw,expected in ((" JADE-OK ","JADE-OK"),(" 4 ","4"),("I can help organize safe JamesOS work.","I can help organize safe JamesOS work.")):
            with self.subTest(raw=raw):result=self.service(raw);self.assertEqual(result["message"],expected);self.assertEqual(result["commands"],[]);self.assertEqual(result["warnings"],[])

    def test_schema_enabled_workspace_chat_uses_actual_http_adapter(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length=int(self.headers.get("Content-Length","0"));requests.append(json.loads(self.rfile.read(length)))
                value={"model":"mistral:instruct","response":json.dumps({"message":"JADE-OK","commands":[],"suggestions":[],"warnings":[]}),"done":True}
                raw=json.dumps(value).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        try:
            config={"ollama":{"host":f"http://127.0.0.1:{server.server_port}","model":"mistral:instruct","endpoint_mode":"generate","timeout_seconds":5}}
            with patch.object(ollama_service,"get_config",return_value=config):
                result=WorkspaceChatService(model=ollama_service.ask_ollama,readiness=lambda:{},root=Path(temporary.name)).message(conversation_id="schema-http-conversation-123456",message="Reply with exactly: JADE-OK",profile=PROFILE,profiles=[PROFILE],workspace={"active_view":"dashboard","form":{}})
        finally:server.shutdown();server.server_close()
        self.assertEqual(result["message"],"JADE-OK");self.assertEqual(result["commands"],[]);self.assertEqual(result["warnings"],[])
        self.assertEqual(len(requests),1);self.assertEqual(requests[0]["model"],"mistral:instruct");self.assertFalse(requests[0]["stream"]);self.assertEqual(requests[0]["format"],OLLAMA_RESPONSE_SCHEMA)
        diagnostic=ollama_service.chat_diagnostics()["generation"];self.assertTrue(diagnostic["schema_supplied"]);self.assertEqual(diagnostic["shape"],"response");self.assertGreater(diagnostic["text_length"],0)

    def test_valid_command_is_returned_and_invalid_set_is_never_partial(self):
        valid=self.service(json.dumps({"message":"Opening","commands":[{"type":"navigate","view":"admin.home"}],"suggestions":[],"warnings":[]}));self.assertEqual(valid["commands"],[{"type":"navigate","view":"admin.home"}])
        malformed='Useful prose\n```json\n{"message":"ignored","commands":[{"type":"navigate","view":"admin.home"},{"type":"publish"}]'
        result=self.service(malformed);self.assertEqual(result["message"],"Useful prose");self.assertEqual(result["commands"],[]);self.assertLessEqual(len(result["warnings"]),1)

    def test_empty_response_uses_hard_error_and_parser_diagnostics_are_bounded(self):
        result=self.service("");self.assertIn("could not safely interpret",result["message"]);self.assertEqual(result["commands"],[])
        diagnostic=application_shell_diagnostics();self.assertEqual(diagnostic["structured_parse"],"failure");self.assertFalse(diagnostic["fallback_used"]);self.assertEqual(diagnostic["commands_count"],0)

    def test_readiness_does_not_overwrite_last_generation(self):
        ollama_service._LAST_GENERATION.update(http_status=200,shape="response",text_length=7,schema_supplied=True,failure_stage="none")
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return json.dumps({"models":[{"name":"mistral:instruct"}]}).encode()
        with patch.object(ollama_service,"get_config",return_value={"ollama":{"host":"http://127.0.0.1:11434","model":"mistral:instruct"}}),patch.object(ollama_service.urllib.request,"urlopen",return_value=Response()):ollama_service.ollama_readiness()
        generation=ollama_service.chat_diagnostics()["generation"];self.assertEqual((generation["http_status"],generation["shape"],generation["text_length"]),(200,"response",7))


if __name__=="__main__":unittest.main()
