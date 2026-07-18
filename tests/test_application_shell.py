from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.application_shell import COMPONENT_REGISTRY,WorkspaceChatService,WorkspaceState,validate_chat_response,validate_ui_command


def profile(profile_id:str,shop_id:int,slug:str)->dict:
    return {"profile_id":profile_id,"profile_type":"commerce_shop","enabled":True,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":slug,"etsy_shop_slug":slug,"listing_tags":["market humor","trader shirt","finance gift","stock market","investor tee","wall street","bear market","bull market","trading humor","portfolio joke","money shirt","unisex tee","graphic shirt"]}}


class ApplicationShellTests(unittest.TestCase):
    def test_app_renders_persistent_two_pane_shell_and_both_shops(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=commerce.new")
        self.assertEqual(response.status_code,200);self.assertIn("class='shell'",response.text);self.assertIn("Your local workspace assistant",response.text);self.assertIn(">JamesOS<",response.text)
        self.assertIn("bagholder-supply",response.text);self.assertIn("unitystitches",response.text);self.assertIn("Commerce Creator",response.text)
        self.assertIn("function navigate(view)",response.text);self.assertIn("textContent",response.text);self.assertIn("function restore(s)",response.text);self.assertIn("Undid local form change",response.text)
        self.assertIn("Local model: desktop",response.text);self.assertIn("GPU: desktop execution host",response.text);self.assertIn("UNPUBLISHED DRAFT ONLY",response.text);self.assertIn("commerce.diagnostics",response.text)
        self.assertNotIn("11434",response.text);self.assertNotIn("Product Studio",response.text);self.assertNotIn("Copilot",response.text)

    def test_app_response_delivers_initialized_application_script(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app")
        self.assertEqual(response.status_code,200)
        for required in ("<script","DOMContentLoaded","/app/chat","/commerce/new","prepare-generation","addEventListener","q('send').onclick","q('undo').onclick","q('stop').onclick","q('retry').onclick","q('reset').onclick","[data-view]"):
            with self.subTest(required=required):self.assertIn(required,response.text)

    def test_app_script_is_inside_returned_body(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            document=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app").text
        script=document.find("<script");closing_script=document.find("</script>",script);closing_body=document.find("</body>")
        self.assertGreaterEqual(script,0);self.assertGreater(closing_script,script);self.assertGreater(closing_body,closing_script)

    def test_chat_endpoint_receives_selected_profile_and_current_form(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")];service=Mock();service.message.return_value={"message":"Ready","commands":[],"suggestions":[],"warnings":[]}
        values={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":"conversation-12345678901234567890","message":"shorten it","active_view":"commerce.new","active_profile_id":"unitystitches","selected_job_id":"","form":{"exact_phrase":"KEEP THIS","product_brief":"Detailed brief"}}
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"WorkspaceChatService",return_value=service),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").post("/app/chat",json=values,headers={"Origin":"http://127.0.0.1:8787"})
        self.assertEqual(response.status_code,200);kwargs=service.message.call_args.kwargs;self.assertEqual(kwargs["profile"]["profile_id"],"unitystitches");self.assertEqual(kwargs["workspace"]["form"]["exact_phrase"],"KEEP THIS")

    def test_structured_commands_are_strict_and_provider_actions_require_confirmation(self):
        ids={"bagholder-supply","unitystitches"}
        result=validate_chat_response({"message":"Prepared","commands":[{"type":"form_patch","fields":{"exact_phrase":"SHORTER"}},{"type":"show_confirmation","action":"start_generation","message":"Confirm destination"}],"suggestions":[],"warnings":[]},ids)
        self.assertEqual(result["commands"][0],{"type":"form_patch","fields":{"exact_phrase":"SHORTER"}});self.assertEqual(result["commands"][1]["type"],"show_confirmation");self.assertEqual(result["commands"][1]["action"],"start_generation")
        with self.assertRaises(ValueError):validate_ui_command({"type":"javascript","code":"alert(1)"},ids)
        with self.assertRaises(ValueError):validate_ui_command({"type":"publish"},ids)
        with self.assertRaises(ValueError):validate_ui_command({"type":"form_patch","fields":{"innerHTML":"<img onerror=alert(1)>"}},ids)

    def test_workspace_chat_uses_existing_ollama_integration_and_never_calls_provider(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];model=Mock(return_value=json.dumps({"message":"I prepared local fields only.","commands":[{"type":"navigate","view":"commerce.new"},{"type":"select_profile","profile_id":"bagholder-supply"},{"type":"form_patch","fields":{"exact_phrase":"UNREALIZED SUPPORT","product_brief":"Bold centered typography for stock market investors"}},{"type":"show_confirmation","action":"start_generation","message":"Confirm destination"}],"suggestions":["Black garment"],"warnings":["Review trademark risk"]}))
        provider=Mock(side_effect=AssertionError("provider must not be called"))
        with tempfile.TemporaryDirectory() as temporary:
            service=WorkspaceChatService(model=model,readiness=lambda:{"ready":True},root=Path(temporary));result=service.message(conversation_id="conversation-12345678901234567890",message="Create a Bagholder shirt",profile=rows[0],profiles=rows,workspace={"active_view":"dashboard","selected_job_id":"","form":{}})
        self.assertEqual(result["commands"][-1]["type"],"show_confirmation");self.assertEqual(result["profile_id"],"bagholder-supply");self.assertIn("format_schema",model.call_args.kwargs);self.assertEqual(model.call_count,1);provider.assert_not_called()

    def test_model_html_is_rejected_and_never_returned(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];model=lambda prompt,**kwargs:json.dumps({"message":"<script>alert(1)</script>","commands":[],"suggestions":[],"warnings":[]})
        with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.application_shell.handle_error",return_value={}):
            result=WorkspaceChatService(model=model,readiness=lambda:{"ready":True},root=Path(temporary)).message(conversation_id="conversation-12345678901234567890",message="review this",profile=rows[0],profiles=rows,workspace={"active_view":"commerce.new","form":{}})
        self.assertNotIn("<script",result["message"]);self.assertEqual(result["commands"],[]);self.assertTrue(result["warnings"])

    def test_workspace_state_and_fixed_component_registry(self):
        state=WorkspaceState("conversation-12345678901234567890",active_view="commerce.new",active_profile_id="bagholder-supply",forms={"commerce.new":{"exact_phrase":"HOLD"}},pending_confirmations=[{"action":"start_generation"}],activity_history=[{"command":"form_patch"}])
        value=state.bounded();self.assertEqual(set(value),{"conversation_id","active_view","active_profile_id","selected_job_id","forms","pending_confirmations","activity_history"})
        self.assertEqual(set(COMPONENT_REGISTRY),{"status_banner","card","text","form","text_input","textarea","radio_cards","tag_list","progress_steps","image_gallery","diagnostic","confirmation","action_bar"})


if __name__=="__main__":unittest.main()
