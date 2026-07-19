import json
import tempfile
import unittest
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
    def test_actual_chat_and_generate_shapes_return_original_prose(self):
        for mode,payload,shape in (("chat",{"message":{"role":"assistant","content":"Hello from chat"}},"message.content"),("generate",{"response":"Hello from generate"},"response")):
            with self.subTest(mode=mode),patch.object(ollama_service,"get_config",return_value={"ollama":{"host":"http://local","model":"test","endpoint_mode":mode}}),patch.object(ollama_service.urllib.request,"urlopen",return_value=Response(payload)) as opened:
                text=ollama_service.ask_ollama("private prompt")
                self.assertEqual(text,"Hello from "+mode);self.assertIn("/api/"+mode,opened.call_args.args[0].full_url);self.assertEqual(ollama_service.chat_diagnostics()["shape"],shape);self.assertNotIn("private prompt",json.dumps(ollama_service.chat_diagnostics()))

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
