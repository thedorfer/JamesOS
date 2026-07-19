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
from jamesos.services.application_shell import COMPONENT_REGISTRY,WorkspaceChatService,WorkspaceState,application_shell_diagnostics,validate_chat_response,validate_ui_command


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
        prep="""<script>window.smokeCalls=[];window.failNext=false;window.uploadSeq=0;window.chatSeq=0;window.fetch=async(url,options={})=>{const path=String(url),method=options.method||'GET';window.smokeCalls.push({path,method,body:options.body||''});let payload={};let status=200;if(path==='/app/chat'){window.chatSeq++;payload=window.failNext?{message:'recoverable failure'}:{message:window.chatSeq===1?'Hello! How can I help?':window.chatSeq===4?'&lt;b&gt;Hello&lt;/b&gt;': 'Mocked locally',commands:[],warnings:[]};if(window.failNext){status=503;window.failNext=false}}else if(path==='/app/chat-diagnostics')payload={readiness:{reachable:true,model:'mistral:instruct',model_installed:true,timestamp:'now'},generation:{timestamp:'now',endpoint_mode:'generate',http_status:200,schema_supplied:true,shape:'response',text_length:7},application_shell:{active_view_id:'admin.home',structured_parse:'success',fallback_used:false,final_message_length:7,commands_count:0,failure_stage:'none'}};else if(path==='/app/attachments'&&method==='POST'){const file=options.body.get('file');payload={attachment_id:'fixture-attachment-id-'+(++window.uploadSeq)+'-safe',filename:file.name,content_type:file.type,size:file.size}}else if(path.startsWith('/app/attachments/')&&method==='DELETE')payload={removed:true};else if(path.startsWith('/app/layouts/'))payload={theme_id:'jamesos-dark',shell:{chat_width:420},panels:[]};else if(path==='/app/health')payload={state:'green',label:'Ready',systems:[]};else if(path==='/app/access-status')payload={access_mode:'loopback',trusted_hostname:'127.0.0.1',https:false,connection_type:'direct',access_scope:'loopback',warning:''};return new Response(JSON.stringify(payload),{status,headers:{'Content-Type':'application/json'}})};</script>"""
        prep=prep.replace("commands:[],warnings:[]}","commands:[],warnings:[],attachment_receipts:(JSON.parse(options.body).attachments||[]).map(a=>({attachment_id:a.attachment_id,filename:a.filename,content_type:a.content_type,byte_count:a.size,ingestion_state:'processed',processing_method:'utf8_text_extraction',extracted_character_count:a.size}))}")
        prep=prep.replace("window.chatSeq++;payload=", "window.chatSeq++;if((JSON.parse(options.body).attachments||[]).length)await new Promise(r=>setTimeout(r,20));payload=")
        prep=prep.replace("window.chatSeq++;if((JSON.parse(options.body).attachments||[]).length)await new Promise(r=>setTimeout(r,20));payload=window.failNext?", "window.chatSeq++;const sent=JSON.parse(options.body).message;if((JSON.parse(options.body).attachments||[]).length)await new Promise(r=>setTimeout(r,20));payload=sent==='Reply with exactly: JADE-OK'?{message:'JADE-OK',commands:[],warnings:[]}:sent==='What is 2 plus 2? Reply with only the number.'?{message:'4',commands:[],warnings:[]}:sent.startsWith('Do not change the workspace')?{message:'The Agency is currently open.',commands:[],warnings:[]}:sent==='Open the Admin workspace.'?{message:'Opening Admin.',commands:[{type:'navigate',view:'admin.home'}],warnings:[]}:window.failNext?")
        prep=prep.replace("window.chatSeq===1?'Hello! How can I help?':window.chatSeq===4?'&lt;b&gt;Hello&lt;/b&gt;'", "sent==='enter message'?'Hello! How can I help?':sent==='html'?'&lt;b&gt;Hello&lt;/b&gt;'")
        smoke="""<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{const wait=()=>new Promise(r=>setTimeout(r,40)),key=(node,key,shift=false)=>node.dispatchEvent(new KeyboardEvent('keydown',{key,shiftKey:shift,bubbles:true,cancelable:true})),choose=async(name)=>{const input=document.getElementById('attachment-input'),dt=new DataTransfer();dt.items.add(new File(['fixture'],name,{type:'text/plain'}));input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));await wait()},commerce=document.getElementById('commerce-new');document.querySelector('[data-view=dashboard]').click();const home=location.search.includes('dashboard')&&!document.getElementById('confirmations').children.length&&getComputedStyle(commerce).display==='none';document.querySelector('[data-view="agency.home"]').click();const agencyView=document.getElementById('agency-view'),merchantButton=document.querySelector('#agency-view [data-view="commerce.new"]'),agency=!agencyView.hidden&&getComputedStyle(commerce).display==='none',merchantVisible=agencyView.querySelector('#agency-registry').offsetParent!==null&&merchantButton.offsetParent!==null&&agencyView.textContent.includes('The Merchant')&&!agencyView.textContent.includes('Registered tools appear here');merchantButton.click();const merchant=location.search.includes('commerce.new')&&!commerce.hidden,commerceSafeguard=getComputedStyle(commerce).display!=='none';document.querySelector('[data-view="admin.home"]').click();const admin=!document.getElementById('admin-view').hidden&&!document.getElementById('confirmations').children.length&&getComputedStyle(commerce).display==='none';let opened=0;const input=document.getElementById('attachment-input'),nativeClick=input.click.bind(input);input.click=()=>{opened++};key(document.getElementById('upload-control'),'Enter');input.click=nativeClick;await choose('remove.txt');const preview=document.getElementById('attachments').textContent.includes('remove.txt');document.querySelector('#attachments button').click();await wait();const box=document.getElementById('chat-message'),before=window.smokeCalls.filter(x=>x.path==='/app/chat').length;box.value='line';key(box,'Enter',true);await wait();const shiftNoSend=window.smokeCalls.filter(x=>x.path==='/app/chat').length===before;box.value='enter message';key(box,'Enter');key(box,'Enter');await wait();const chatCalls=window.smokeCalls.filter(x=>x.path==='/app/chat'),enterOnce=chatCalls.length===before+1,removedBody=JSON.parse(chatCalls.at(-1).body),plainHello=document.getElementById('transcript').textContent.includes('Hello! How can I help?')&&!document.getElementById('transcript').textContent.includes('could not safely interpret');await choose('success.txt');box.value='success';key(box,'Enter');await wait();const cleared=!document.getElementById('attachments').children.length;await choose('failure.txt');window.failNext=true;box.value='failure';key(box,'Enter');await wait();const preserved=document.getElementById('attachments').textContent.includes('failure.txt');box.value='html';key(box,'Enter');await wait();const inert=document.getElementById('transcript').textContent.includes('&lt;b&gt;Hello&lt;/b&gt;')&&!document.getElementById('transcript').querySelector('b');const oldConversation=localStorage.getItem('jamesos-conversation-id');document.getElementById('reset').click();const reset=oldConversation!==localStorage.getItem('jamesos-conversation-id')&&!document.getElementById('transcript').children.length;const result={ready:document.documentElement.dataset.jamesosReady,home,agency,admin,merchant,merchantVisible,commerceSafeguard,opened,preview,shiftNoSend,enterOnce,plainHello,inert,removedExcluded:removedBody.attachments.length===0,cleared,preserved,reset,providerCalls:window.smokeCalls.filter(x=>/ollama|printify|etsy|comfy/i.test(x.path)).length,published:window.smokeCalls.some(x=>/publish|approve/.test(x.path)),orders:window.smokeCalls.some(x=>/order/.test(x.path))};const out=document.createElement('pre');out.id='smoke-result';out.textContent=JSON.stringify(result);document.body.append(out)},100));</script>"""
        smoke=smoke.replace("const merchant=location.search.includes('commerce.new')&&!commerce.hidden,commerceSafeguard=", "const freshTitle=document.getElementById('listing_title').value==='',title=document.getElementById('listing_title');title.value='Manual title';title.dispatchEvent(new Event('input',{bubbles:true}));const profile=document.getElementById('commerce-profile');profile.selectedIndex=1;profile.dispatchEvent(new Event('change',{bubbles:true}));const manualTitle=title.value==='Manual title',merchant=location.search.includes('commerce.new')&&!commerce.hidden,commerceSafeguard=")
        smoke=smoke.replace("const preview=document.getElementById('attachments').textContent.includes('remove.txt')", "const preview=document.getElementById('attachments').textContent.includes('Attached: remove.txt — ready to send')")
        smoke=smoke.replace("const admin=!document.getElementById('admin-view').hidden&&!document.getElementById('confirmations').children.length&&getComputedStyle(commerce).display==='none';", "const admin=!document.getElementById('admin-view').hidden&&!document.getElementById('confirmations').children.length&&getComputedStyle(commerce).display==='none',adminForm=document.querySelector('[data-profile-settings=\"bagholder-supply\"]'),adminInput=adminForm.elements.display_name,adminLocked=adminInput.readOnly,adminOriginal=adminInput.value;adminForm.querySelector('[data-profile-edit]').click();const adminEditing=!adminInput.readOnly;adminInput.value='Temporary change';adminForm.querySelector('[data-profile-cancel]').click();const adminCanceled=adminInput.readOnly&&adminInput.value===adminOriginal;adminForm.querySelector('[data-profile-edit]').click();adminInput.value='Saved display';adminForm.requestSubmit();await wait();const adminSaved=adminInput.readOnly&&window.smokeCalls.some(x=>x.path==='/app/admin/commerce-profiles/bagholder-supply'&&x.method==='POST');")
        smoke=smoke.replace("let opened=0;const input=", "document.querySelector('[data-view=\"agency.home\"]').click();const groundedBox=document.getElementById('chat-message');for(const prompt of ['Reply with exactly: JADE-OK','What is 2 plus 2? Reply with only the number.','Do not change the workspace. Tell me which workspace is currently open.','Open the Admin workspace.']){groundedBox.value=prompt;key(groundedBox,'Enter');await wait()}const assistantTurns=[...document.querySelectorAll('#transcript .assistant')].map(x=>x.textContent),exactJade=assistantTurns.includes('JamesOS: JADE-OK'),exactMath=assistantTurns.includes('JamesOS: 4'),agencyGrounded=assistantTurns.includes('JamesOS: The Agency is currently open.')&&!assistantTurns.some(x=>x.includes('Bagholder Supply Co. workspace')),adminCommand=assistantTurns.includes('JamesOS: Opening Admin.')&&!document.getElementById('admin-view').hidden;let opened=0;const input=")
        smoke=smoke.replace("box.value='success';key(box,'Enter');await wait();", "box.value='success';key(box,'Enter');const processing=document.getElementById('attachments').textContent.includes('Processing: success.txt');await wait();")
        smoke=smoke.replace("const cleared=", "const processed=document.getElementById('transcript').textContent.includes('Processed: success.txt')&&document.getElementById('attachments').textContent.indexOf('success.txt')<0;const cleared=").replace("commerceSafeguard,opened", "commerceSafeguard,freshTitle,manualTitle,processing,processed,opened")
        smoke=smoke.replace("document.getElementById('reset').click();const reset=", "document.getElementById('reset').click();await wait();const diagnosticCalls=window.smokeCalls.filter(x=>x.path==='/app/chat-diagnostics').length,diagnosticText=document.getElementById('chat-generation').textContent+' | '+document.getElementById('chat-parsing').textContent,diagnosticsLive=diagnosticCalls>=window.smokeCalls.filter(x=>x.path==='/app/chat').length+1&&diagnosticText.includes('HTTP status: 200')&&diagnosticText.includes('Structured parse: success');const reset=")
        smoke=smoke.replace("processed,opened", "processed,diagnosticsLive,diagnosticCalls,diagnosticText,opened")
        smoke=smoke.replace("diagnosticText,opened", "diagnosticText,exactJade,exactMath,agencyGrounded,adminCommand,opened")
        smoke=smoke.replace("home,agency,admin,merchant", "home,agency,admin,adminLocked,adminEditing,adminCanceled,adminSaved,merchant")
        document=response.text.replace("<script>document.addEventListener",prep+"<script>document.addEventListener",1).replace("</body>",smoke+"</body>")
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
            browser=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--enable-logging=stderr","--virtual-time-budget=2500","--dump-dom",f"http://127.0.0.1:{server.server_port}/app"],check=True,capture_output=True,text=True);rendered=browser.stdout
        finally:server.shutdown();server.server_close()
        if '<pre id="smoke-result">' not in rendered:self.fail("Browser smoke did not complete:\n"+browser.stderr[-4000:]+"\n"+rendered[-1000:])
        marker=rendered.split('<pre id="smoke-result">',1)[1].split("</pre>",1)[0].replace("&quot;",'"');result=json.loads(marker)
        self.assertEqual(result["ready"],"true")
        for key in ("home","agency","admin","adminLocked","adminEditing","adminCanceled","adminSaved","merchant","merchantVisible","commerceSafeguard","freshTitle","manualTitle","processing","processed","diagnosticsLive","exactJade","exactMath","agencyGrounded","adminCommand","preview","shiftNoSend","enterOnce","plainHello","inert","removedExcluded","cleared","preserved","reset"):self.assertTrue(result[key],f"{key}: {result}")
        self.assertEqual(result["opened"],1)
        self.assertEqual(result["providerCalls"],0);self.assertFalse(result["published"]);self.assertFalse(result["orders"])

    def test_app_renders_persistent_two_pane_shell_and_both_shops(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app?view=commerce.new")
        self.assertEqual(response.status_code,200);self.assertIn("class='shell'",response.text);self.assertIn("Chat with Jade",response.text);self.assertIn(">JamesOS<",response.text)
        self.assertIn(">Clear</button>",response.text);self.assertNotIn("Reset conversation",response.text);self.assertIn("Private chat",response.text)
        self.assertIn("bagholder-supply",response.text);self.assertIn("unitystitches",response.text);self.assertIn("Product Studio",response.text)
        self.assertIn("function navigate(view)",response.text);self.assertIn("textContent",response.text)
        self.assertIn("id='health-dot'",response.text);self.assertIn("System health",response.text);self.assertIn("UNPUBLISHED DRAFT ONLY",response.text);self.assertIn("commerce.diagnostics",response.text)
        self.assertNotIn("11434",response.text);self.assertNotIn("panel-title'>Commerce Creator",response.text);self.assertNotIn("Copilot",response.text)
        for removed in ("id='stop'","id='retry'","id='undo'","bind('stop','click'","bind('retry','click'","bind('undo','click'"):self.assertNotIn(removed,response.text)

    def test_app_response_delivers_initialized_application_script(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app")
        self.assertEqual(response.status_code,200)
        for required in ("<script","DOMContentLoaded","/app/chat","/app/attachments","/commerce/new","prepare-generation","addEventListener","bind('send','click'","bind('reset','click'","bind('chat-message','keydown'","[data-view]","jamesosReady='true'"):
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

    def test_malformed_structured_response_uses_only_safe_plain_text(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];model=Mock(return_value='A safe plain response, with no commands.')
        provider=Mock(side_effect=AssertionError("fallback cannot call providers"))
        with tempfile.TemporaryDirectory() as temporary:
            result=WorkspaceChatService(model=model,readiness=lambda:{"ready":True},root=Path(temporary)).message(conversation_id="conversation-12345678901234567890",message="ordinary question",profile=rows[0],profiles=rows,workspace={"active_view":"dashboard","form":{"exact_phrase":"UNCHANGED"}})
        self.assertEqual(result["message"],'A safe plain response, with no commands.');self.assertEqual(result["commands"],[]);self.assertEqual(result["warnings"],[]);self.assertEqual(result["profile_id"],"bagholder-supply");provider.assert_not_called()

    def test_realistic_ollama_prose_before_malformed_structure_is_preserved_without_repair(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        raw='Hello! How can I help?\n```json\n{"message":"ignored","commands":[{"type":"navigate","view":"commerce.new"}]'
        requests=[];provider=Mock(side_effect=AssertionError("fallback cannot call providers"))
        class OllamaHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length=int(self.headers.get("Content-Length","0"));requests.append(json.loads(self.rfile.read(length)));body=json.dumps({"model":"local-test","response":raw,"done":True}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),OllamaHandler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            config={"ollama":{"host":f"http://127.0.0.1:{server.server_port}","model":"local-test","timeout_seconds":5}}
            values={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":"conversation-12345678901234567890","message":"hello","active_view":"dashboard","active_profile_id":"bagholder-supply","selected_job_id":"","form":{"exact_phrase":"UNCHANGED"},"attachments":[]}
            with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.ollama_service.get_config",return_value=config),patch("jamesos.services.application_shell.ROOT",Path(temporary)),patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"_require_local"):
                response=TestClient(api.app,base_url="http://127.0.0.1:8787").post("/app/chat",json=values,headers={"Origin":"http://127.0.0.1:8787"});result=response.json()
        finally:server.shutdown();server.server_close()
        self.assertEqual(response.status_code,200);self.assertEqual(result["message"],"Hello! How can I help?");self.assertEqual(result["commands"],[]);self.assertEqual(result["warnings"],["No workspace changes were applied."]);self.assertNotIn("could not safely interpret",result["message"]);self.assertEqual(len(requests),1);self.assertIn("format",requests[0]);provider.assert_not_called()

    def test_adapter_without_usable_text_keeps_hard_safe_error(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.application_shell.handle_error",return_value={}) as logged:
            result=WorkspaceChatService(model=Mock(return_value='{"commands":['),readiness=lambda:{"ready":True},root=Path(temporary)).message(conversation_id="conversation-12345678901234567890",message="hello",profile=rows[0],profiles=rows,workspace={"active_view":"dashboard","form":{}})
        self.assertEqual(result["message"],"JamesOS could not safely interpret the local model response. Try again.");self.assertEqual(result["commands"],[]);self.assertEqual(result["warnings"],["No workspace changes were applied."]);logged.assert_called_once()

    def test_malformed_commands_are_never_partially_applied_and_html_is_inert(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        malformed='{"message":"Safe explanation","commands":[{"type":"navigate","view":"commerce.new"},{"type":"publish"}]'
        with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.application_shell.handle_error",return_value={}):
            result=WorkspaceChatService(model=Mock(return_value=malformed),readiness=lambda:{"ready":True},root=Path(temporary)).message(conversation_id="conversation-12345678901234567890",message="review",profile=rows[0],profiles=rows,workspace={"active_view":"dashboard","form":{"exact_phrase":"UNCHANGED"}})
        self.assertEqual(result["message"],"Safe explanation");self.assertEqual(result["commands"],[])
        html=malformed.replace("Safe explanation","<img src=x onerror=alert(1)>")
        with tempfile.TemporaryDirectory() as temporary,patch("jamesos.services.application_shell.handle_error",return_value={}):
            blocked=WorkspaceChatService(model=Mock(return_value=html),readiness=lambda:{"ready":True},root=Path(temporary)).message(conversation_id="conversation-12345678901234567890",message="review",profile=rows[0],profiles=rows,workspace={"active_view":"dashboard","form":{}})
        self.assertNotIn("<img",blocked["message"]);self.assertEqual(blocked["commands"],[])

    def test_conversation_contract_prioritizes_exact_answers_and_active_view(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];prompts=[]
        def model(prompt,**kwargs):
            prompts.append(prompt);user=prompt.rsplit("\nUser: ",1)[1]
            if user.startswith("Reply with exactly"):message="JADE-OK"
            elif user.startswith("What is 2 plus 2"):message="4"
            else:message="The Agency is currently open."
            return json.dumps({"message":message,"commands":[],"suggestions":[],"warnings":[]})
        with tempfile.TemporaryDirectory() as temporary:
            service=WorkspaceChatService(model=model,readiness=lambda:{},root=Path(temporary))
            results=[service.message(conversation_id="grounding-conversation-123456",message=text,profile=rows[0],profiles=rows,workspace={"active_view":"agency.home","form":{}}) for text in ("Reply with exactly: JADE-OK","What is 2 plus 2? Reply with only the number.","Do not change the workspace. Tell me which workspace is currently open.")]
        self.assertEqual([item["message"] for item in results],["JADE-OK","4","The Agency is currently open."]);self.assertTrue(all(item["commands"]==[] and item["warnings"]==[] for item in results))
        self.assertTrue(all("Active view ID: agency.home" in item and "Active view title: The Agency" in item and "Active profile ID (not the workspace): bagholder-supply" in item for item in prompts))

    def test_navigation_contract_returns_one_validated_command_and_natural_confirmation(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        model=Mock(return_value=json.dumps({"message":"Opening Admin.","commands":[{"type":"navigate","view":"admin.home"}],"suggestions":[],"warnings":[]}))
        with tempfile.TemporaryDirectory() as temporary:
            result=WorkspaceChatService(model=model,readiness=lambda:{},root=Path(temporary)).message(conversation_id="navigation-conversation-123456",message="Open the Admin workspace.",profile=rows[0],profiles=rows,workspace={"active_view":"agency.home","form":{}})
        self.assertEqual(result["message"],"Opening Admin.");self.assertEqual(result["commands"],[{"type":"navigate","view":"admin.home"}]);self.assertEqual(application_shell_diagnostics()["active_view_id"],"agency.home")

    def test_product_studio_guidance_is_substantive_preserves_multiline_and_manual_fields(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];fields={"exact_phrase":"UNREALIZED LOSSES\nBUILD CHARACTER","listing_title":"Unrealized Losses Market Humor Unisex T-Shirt","product_brief":"Create original centered typography artwork with strong readability, a warm high-contrast artwork palette kept separate from garment colors, transparent background, balanced composition for market-humor audiences, and no trademarks or third-party branding.","special_instructions":"Preserve the exact multiline phrase. Keep artwork colors separate from garment colors. Require a transparent background and exactly 13 Etsy tags. Unpublished draft only; no publication and no order."}
        model=Mock(return_value=json.dumps({"message":"Prepared substantive Product Studio fields.","commands":[{"type":"form_patch","fields":fields}],"suggestions":[],"warnings":[]}))
        with tempfile.TemporaryDirectory() as temporary:
            result=WorkspaceChatService(model=model,readiness=lambda:{},root=Path(temporary)).message(conversation_id="product-guidance-conversation-123",message="Fill out Product Studio for a shirt that says:\nUNREALIZED LOSSES\nBUILD CHARACTER",profile=rows[0],profiles=rows,workspace={"active_view":"commerce.new","form":{"listing_title":"Manual title"}})
        patch_fields=result["commands"][0]["fields"];self.assertEqual(patch_fields["exact_phrase"],fields["exact_phrase"]);self.assertNotIn("listing_title",patch_fields);self.assertIn("transparent",patch_fields["product_brief"]);self.assertFalse(any(item.get("type")=="show_confirmation" for item in result["commands"]))
        self.assertNotIn("Your unique product description",json.dumps(result));self.assertIn("expert Product Studio guide",model.call_args.args[0])

    def test_live_chat_diagnostics_endpoint_is_sanitized_and_readiness_preserves_generation(self):
        generation={"endpoint_mode":"generate","http_status":200,"schema_supplied":True,"top_level_keys":["done","response"],"shape":"response","text_length":7,"exception_type":None,"failure_stage":"none","timestamp":"generation-time"}
        diagnostic={"readiness":{"reachable":True,"model_installed":True,"model":"mistral:instruct","timestamp":"ready-time"},"generation":generation}
        with patch.object(api,"_require_local"),patch.object(api,"ollama_readiness",return_value={"ready":True}),patch.object(api,"chat_diagnostics",return_value=diagnostic):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app/chat-diagnostics")
        self.assertEqual(response.status_code,200);value=response.json();self.assertEqual(value["generation"],generation);self.assertIn("active_view_id",value["application_shell"]);self.assertEqual(response.headers["cache-control"],"no-store")
        serialized=json.dumps(value);self.assertNotIn("prompt",serialized.casefold());self.assertNotIn("/home/",serialized)

    def test_confirmation_is_absent_until_pending_and_adjacent_to_protected_action(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            text=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app").text
        self.assertNotIn("data-panel-id='external_confirmation'",text);self.assertIn("<div id='confirmations' data-component='confirmation'></div><button type='button' id='prepare-generation'",text)
        self.assertIn("Requested action:",text);self.assertIn("External provider contacted:",text);self.assertIn("Irreversible publication/submission:",text)

    def test_workspace_state_and_fixed_component_registry(self):
        state=WorkspaceState("conversation-12345678901234567890",active_view="commerce.new",active_profile_id="bagholder-supply",forms={"commerce.new":{"exact_phrase":"HOLD"}},pending_confirmations=[{"action":"start_generation"}],activity_history=[{"command":"form_patch"}])
        value=state.bounded();self.assertEqual(set(value),{"conversation_id","active_view","active_profile_id","selected_job_id","forms","pending_confirmations","activity_history"})
        self.assertEqual(set(COMPONENT_REGISTRY),{"status_banner","card","text","form","text_input","textarea","radio_cards","tag_list","progress_steps","image_gallery","diagnostic","confirmation","action_bar"})


if __name__=="__main__":unittest.main()
