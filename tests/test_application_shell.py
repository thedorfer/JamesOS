from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.application_shell import COMPONENT_REGISTRY,WorkspaceChatService,WorkspaceState,validate_chat_response,validate_ui_command


def profile(profile_id:str,shop_id:int,slug:str)->dict:
    return {"profile_id":profile_id,"profile_type":"commerce_shop","enabled":True,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":slug,"etsy_shop_slug":slug,"listing_tags":["market humor","trader shirt","finance gift","stock market","investor tee","wall street","bear market","bull market","trading humor","portfolio joke","money shirt","unisex tee","graphic shirt"]}}


class ApplicationShellTests(unittest.TestCase):
    def test_actual_app_bootstrap_runs_in_browser_and_binds_safe_shell_controls(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required for the shell smoke test")
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers["content-security-policy"],"default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        smoke="""<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{const calls=[],original=window.fetch;window.fetch=async(url,options={})=>{const path=String(url);calls.push({path,method:options.method||'GET',body:options.body||''});if(path==='/app/chat')return new Response(JSON.stringify({message:'Mocked locally',commands:[],warnings:[]}),{status:200,headers:{'Content-Type':'application/json'}});return original(url,options)};document.querySelector('[data-view=dashboard]').click();const home=location.search.includes('dashboard');document.querySelector('[data-view="agency.home"]').click();const agency=!document.getElementById('agency-view').hidden;document.querySelector('[data-view="admin.home"]').click();const admin=!document.getElementById('admin-view').hidden;document.getElementById('health-dot').click();const health=!document.getElementById('health-detail').hidden;document.getElementById('customize-layout').click();const customize=document.body.classList.contains('customizing');document.getElementById('exact_phrase').value='CURRENT FORM';document.getElementById('chat-message').value='smoke message';document.getElementById('send').click();await new Promise(resolve=>setTimeout(resolve,100));const chat=calls.find(call=>call.path==='/app/chat'),body=JSON.parse(chat.body);const result={ready:document.documentElement.dataset.jamesosReady,home,agency,admin,health,customize,initError:!document.getElementById('shell-init-error').hidden,chatMethod:chat.method,body,providerCalls:calls.filter(call=>/ollama|printify|etsy|comfy/i.test(call.path)).length,published:calls.some(call=>/publish|approve/.test(call.path)),orders:calls.some(call=>/order/.test(call.path))};const out=document.createElement('pre');out.id='smoke-result';out.textContent=JSON.stringify(result);document.body.append(out)},100));</script>"""
        document=response.text.replace("<button type='button' id='close-chat' class='drawer-toggle'>Close</button>","").replace("</body>",smoke+"</body>")
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/app/layouts/"):payload={"theme_id":"jamesos-dark","shell":{"chat_width":420},"panels":[]}
                elif self.path=="/app/health":payload={"state":"green","label":"Ready","systems":[]}
                elif self.path=="/app/access-status":payload={"access_mode":"loopback","trusted_hostname":"127.0.0.1","https":False,"connection_type":"direct","access_scope":"loopback","warning":""}
                else:
                    raw=document.encode();self.send_response(200);self.send_header("Content-Type","text/html");self.send_header("Content-Security-Policy",response.headers["content-security-policy"]);self.end_headers();self.wfile.write(raw);return
                raw=json.dumps(payload).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=1500","--dump-dom",f"http://127.0.0.1:{server.server_port}/app"],check=True,capture_output=True,text=True).stdout
        finally:server.shutdown();server.server_close()
        marker=rendered.split('<pre id="smoke-result">',1)[1].split("</pre>",1)[0].replace("&quot;",'"');result=json.loads(marker)
        self.assertEqual(result["ready"],"true");self.assertTrue(result["home"]);self.assertTrue(result["agency"]);self.assertTrue(result["admin"]);self.assertTrue(result["health"]);self.assertTrue(result["customize"]);self.assertTrue(result["initError"]);self.assertEqual(result["chatMethod"],"POST")
        self.assertEqual(result["body"]["active_view"],"admin.home");self.assertEqual(result["body"]["active_profile_id"],"bagholder-supply");self.assertEqual(result["body"]["form"]["exact_phrase"],"CURRENT FORM");self.assertTrue(result["body"]["csrf_token"]);self.assertTrue(result["body"]["conversation_id"])
        self.assertEqual(result["providerCalls"],0);self.assertFalse(result["published"]);self.assertFalse(result["orders"])

    def test_app_renders_persistent_two_pane_shell_and_both_shops(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=commerce.new")
        self.assertEqual(response.status_code,200);self.assertIn("class='shell'",response.text);self.assertIn("Your local workspace assistant",response.text);self.assertIn(">JamesOS<",response.text)
        self.assertIn("bagholder-supply",response.text);self.assertIn("unitystitches",response.text);self.assertIn("Commerce Creator",response.text)
        self.assertIn("function navigate(view)",response.text);self.assertIn("textContent",response.text);self.assertIn("function restore(s)",response.text);self.assertIn("Undid local form change",response.text)
        self.assertIn("id='health-dot'",response.text);self.assertIn("System health",response.text);self.assertIn("UNPUBLISHED DRAFT ONLY",response.text);self.assertIn("commerce.diagnostics",response.text)
        self.assertNotIn("11434",response.text);self.assertNotIn("Product Studio",response.text);self.assertNotIn("Copilot",response.text)

    def test_app_response_delivers_initialized_application_script(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app")
        self.assertEqual(response.status_code,200)
        for required in ("<script","DOMContentLoaded","/app/chat","/commerce/new","prepare-generation","addEventListener","bind('send','click'","bind('undo','click'","bind('stop','click'","bind('retry','click'","bind('reset','click'","[data-view]","jamesosReady='true'"):
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
