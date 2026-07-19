import json
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from jamesos.services import ollama_service
from jamesos.services.application_shell import WorkspaceChatService


class Response:
    def __init__(self,value,status=200):self.value=value;self.status=status
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.value).encode()


class OllamaChatContractTests(unittest.TestCase):
    def test_local_http_adapter_integration_accepts_real_generate_envelope(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length=int(self.headers.get("Content-Length","0"));requests.append(json.loads(self.rfile.read(length)));raw=json.dumps({"model":"mistral:instruct","response":" JADE-OK","done":True}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with patch.object(ollama_service,"get_config",return_value={"ollama":{"host":f"http://127.0.0.1:{server.server_port}","model":"mistral:instruct","endpoint_mode":"generate","timeout_seconds":5}}):result=ollama_service.ask_ollama("Reply with exactly: JADE-OK")
        finally:server.shutdown();server.server_close()
        self.assertEqual(result,"JADE-OK");self.assertEqual(len(requests),1);self.assertEqual(ollama_service.chat_diagnostics()["http_status"],200);self.assertEqual(ollama_service.chat_diagnostics()["shape"],"response")
    def test_actual_chat_and_generate_shapes_return_original_prose(self):
        for mode,payload,shape,expected in (("chat",{"model":"mistral:instruct","message":{"role":"assistant","content":" Hello from chat "},"done":True},"message.content","Hello from chat"),("generate",{"model":"mistral:instruct","response":" JADE-OK ","done":True},"response","JADE-OK")):
            with self.subTest(mode=mode),patch.object(ollama_service,"get_config",return_value={"ollama":{"host":"http://local","model":"test","endpoint_mode":mode}}),patch.object(ollama_service.urllib.request,"urlopen",return_value=Response(payload)) as opened:
                text=ollama_service.ask_ollama("private prompt")
                self.assertEqual(text,expected);self.assertIn("/api/"+mode,opened.call_args.args[0].full_url);self.assertEqual(ollama_service.chat_diagnostics()["shape"],shape);self.assertEqual(ollama_service.chat_diagnostics()["text_length"],len(expected));self.assertNotIn("private prompt",json.dumps(ollama_service.chat_diagnostics()))

    def test_unsupported_shape_is_sanitized_and_private_chat_is_not_persisted(self):
        with patch.object(ollama_service,"get_config",return_value={"ollama":{"host":"http://local","model":"test"}}),patch.object(ollama_service.urllib.request,"urlopen",return_value=Response({"done":True})):
            with self.assertRaises(RuntimeError):ollama_service.ask_ollama("private prompt")
        diagnostic=ollama_service.chat_diagnostics();self.assertEqual(diagnostic["failure_stage"],"response_shape");self.assertNotIn("private prompt",json.dumps(diagnostic))
        profile={"profile_id":"p","display_name":"P","configuration":{"printify_shop_id":1,"etsy_shop_slug":"P"}}
        model=Mock(return_value=json.dumps({"message":"Private answer","commands":[],"suggestions":[],"warnings":[]}))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);result=WorkspaceChatService(model=model,readiness=lambda:{},root=root).message(conversation_id="private-conversation-123456",message="do not save me",profile=profile,profiles=[profile],workspace={"form":{}},ephemeral=True)
            self.assertEqual(result["message"],"Private answer");self.assertFalse(list(root.glob("*.json")))

if __name__=="__main__":unittest.main()
