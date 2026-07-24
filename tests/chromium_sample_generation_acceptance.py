"""Chromium acceptance for the Coloring Book Producer confirmed sample flow.

All mutating sample requests are fulfilled inside Chromium's DevTools network
interceptor. The real API supplies only the delivered HTML and read-only project
detail, so this script cannot submit a real ComfyUI prompt.
"""
from __future__ import annotations

import json
import subprocess
import socket
import tempfile
import threading
import time
import urllib.request

import websocket

PROJECT = "book-project-20260719T224438-d0cba878"
BASE = "http://127.0.0.1:8787"
GENERATE = f"/projects/{PROJECT}/samples/generate"
RETRY = f"/projects/{PROJECT}/samples/retry"
SAMPLES = f"/projects/{PROJECT}/samples"
REFERENCE = "/reference"
IDENTITY = {
    "project_id": PROJECT,
    "page_plan_revision": 1,
    "page_plan_hash": "b" * 64,
    "selected_page_ids": ["page-001", "page-005", "page-015"],
    "workflow_profile": "kids-bold-line-art-v1",
    "workflow": "kids-bold-line-art-v1.api.json",
    "workflow_hash": "c" * 64,
    "checkpoint": "DreamShaper.safetensors",
    "request_id": f"samples-{PROJECT}-bbbbbbbbbbbb",
    "generation_identity": "d" * 64,
}
PREVIEW = {
    "confirmation_required": True,
    **IDENTITY,
    "provider_readiness": {"configured": True, "status": "ready"},
    "output_directory": "/test/fake-samples",
}
ARTIFACT = {
    "asset_id": "fake-sample-page-001",
    "page_id": "page-001",
    "prompt_id": "prompt-001",
    "provider_id": "fake-local-creative",
    "workflow_hash": IDENTITY["workflow_hash"],
    "model_checkpoint": IDENTITY["checkpoint"],
    "seed": 1,
    "width": 1024,
    "height": 1280,
    "file_sha256": "e" * 64,
    "review_state": "pending",
    "technical_validation": {"valid": True},
}
ARTIFACTS = [
    {
        **ARTIFACT,
        "asset_id": f"fake-sample-{page_id}",
        "page_id": page_id,
        "prompt_id": f"prompt-{page_id[-3:]}",
        "file_sha256": str(index) * 64,
    }
    for index, page_id in enumerate(IDENTITY["selected_page_ids"], 1)
]


class Browser:
    def __init__(self, mode: str):
        self.mode = mode
        self.progress_state = "provider_submitted" if mode in {"progress_active","single_regen_active"} else None
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0));self.port=probe.getsockname()[1]
        self.profile = tempfile.TemporaryDirectory()
        self.chrome = subprocess.Popen(
            [
                "google-chrome",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={self.profile.name}",
                f"{BASE}/app?view=agency.coloring-book-producer&project_id={PROJECT}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                tab = next(x for x in tabs if x.get("url", "").startswith(BASE))
                break
            except Exception:
                time.sleep(0.05)
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"])
        self.serial = 0
        self.responses = {}
        self.dialogs = []
        self.preview_bodies = []
        self.confirmed_bodies = []
        self.retry_preview_bodies = []
        self.retry_confirmed_bodies = []
        self.sample_gets = 0
        self.reference_bodies = []
        self.reference_asset_id = None
        self.confirmed_paused = threading.Event()
        self.confirmed_request_id = None
        self.running = True
        threading.Thread(target=self._reader, daemon=True).start()
        self.send("Runtime.enable")
        self.send("Page.enable")
        self.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})

    def send(self, method, params=None):
        self.serial += 1
        call_id = self.serial
        self.ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        return call_id

    def evaluate(self, expression):
        call_id = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        for _ in range(100):
            if call_id in self.responses:
                return self.responses.pop(call_id)["result"]["result"].get("value")
            time.sleep(0.02)
        raise AssertionError(f"Chromium evaluation timed out: {expression}")

    def fulfill(self, request_id, value, status=200):
        body = json.dumps(value).encode()
        import base64

        self.send(
            "Fetch.fulfillRequest",
            {
                "requestId": request_id,
                "responseCode": status,
                "responseHeaders": [{"name": "Content-Type", "value": "application/json"}],
                "body": base64.b64encode(body).decode(),
            },
        )

    def _reader(self):
        while self.running:
            try:
                value = json.loads(self.ws.recv())
            except Exception:
                return
            if "id" in value:
                self.responses[value["id"]] = value
                continue
            method = value.get("method")
            params = value.get("params", {})
            if method == "Page.javascriptDialogOpening":
                self.dialogs.append(params.get("message", ""))
                self.send("Page.handleJavaScriptDialog", {"accept": self.mode != "cancel"})
            elif method == "Fetch.requestPaused":
                request_id = params["requestId"]
                request = params["request"]
                url = request["url"]
                if GENERATE in url:
                    body = json.loads(request.get("postData") or "{}")
                    if body.get("confirmed") is True:
                        self.confirmed_bodies.append(body)
                        self.confirmed_paused.set()
                        if self.mode == "network":
                            self.send("Fetch.failRequest", {"requestId": request_id, "errorReason": "Aborted"})
                            continue
                        self.confirmed_request_id = request_id
                        self.finish_confirmed()
                    else:
                        self.preview_bodies.append(body)
                        self.fulfill(request_id, PREVIEW)
                elif RETRY in url:
                    body=json.loads(request.get("postData") or "{}")
                    retry_preview={**IDENTITY,"confirmation_required":True,"retry_page_ids":["page-001"],"retry_pages":[{"page_id":"page-001","title":"Arrival And Unpacking Adventure 1"}],"original_lost_prompt_id":"lost-prompt","comfyui_instance_identity":{"instance_id":"current-instance"},"retry_attempt":1,"retry_identity":"f"*64,"confirmation":"Retry page-001 only after the lost prompt? No marketplace action will occur."}
                    if body.get("confirmed") is True:
                        self.retry_confirmed_bodies.append(body);time.sleep(.2)
                        if self.mode=="retry_failure":self.fulfill(request_id,{"detail":"simulated retry provider failure"},502)
                        else:self.fulfill(request_id,{"status":"failed","operation_state":"remaining_samples_authorized","artifact_count":1,"artifacts":[ARTIFACTS[0]],"retry_page_ids":["page-005","page-015"]})
                    else:self.retry_preview_bodies.append(body);self.fulfill(request_id,retry_preview)
                elif REFERENCE in url and request["method"]=="POST":
                    body=json.loads(request.get("postData") or "{}");self.reference_bodies.append(body);self.reference_asset_id=url.split("/samples/",1)[1].split("/",1)[0];self.fulfill(request_id,{"reference_asset_id":self.reference_asset_id,"planning_metadata_only":True,"approval":False,"external_actions":0})
                elif SAMPLES in url and request["method"] == "GET":
                    self.sample_gets += 1
                    generated = bool(self.confirmed_bodies) and self.mode == "success"
                    retry_mode=self.mode.startswith("retry")
                    retry_done=bool(self.retry_confirmed_bodies) and self.mode=="retry_success"
                    progress_state=self.progress_state or ("failed" if self.mode=="progress_failure" else "retry_authorized" if self.mode=="progress_retry" else "review_ready" if self.mode=="progress_completion" else "remaining_samples_authorized" if retry_done else "retry_authorized" if retry_mode else "review_ready" if generated else "not_generated")
                    progress_active=progress_state in {"previewed","submission_started","provider_submitted","running","outputs_received"}
                    progress_artifacts=ARTIFACTS if progress_state=="review_ready" else []
                    candidates=[{**ARTIFACTS[0],"asset_id":"candidate-first","generated_at":"2026-07-23T15:41:36-05:00","profile_id":"kids-bold-line-art-v1","prompt_revision":1,"output_designation":"raw","reference_candidate":self.reference_asset_id=="candidate-first"},{**ARTIFACTS[0],"asset_id":"candidate-newest","generated_at":"2026-07-23T16:38:04-05:00","profile_id":"kids-bold-line-art-v6","prompt_revision":2,"output_designation":"processed","reference_candidate":self.reference_asset_id=="candidate-newest","technical_validation":{"valid":False,"failed_reasons":["mostly white background","dark pixel ratio","largest black component","safe margins","excessive grayscale"]},"validation_failed_reasons":["mostly white background","dark pixel ratio","largest black component","safe margins","excessive grayscale"]}]
                    if self.mode=="single_regen_active" and progress_state=="review_ready":candidates.append({**ARTIFACTS[0],"asset_id":"candidate-revision-3","generated_at":"2026-07-23T17:10:00-05:00","profile_id":"kids-bold-line-art-v6","prompt_revision":3,"positive_prompt_hash":"c"*64,"negative_prompt_hash":"d"*64,"generation_attempt_identity":"e"*64,"comfyui_prompt_id":"new-revision-3-prompt","output_designation":"processed"})
                    displayed_artifacts=candidates if self.mode=="single_regen_active" else [{**ARTIFACTS[0],"profile_id":"kids-bold-line-art-v2","technical_validation":{"valid":False,"failed_reasons":["largest black component","safe margins"]},"validation_failed_reasons":["largest black component","safe margins"]}] if self.mode=="validation_invalid" else ARTIFACTS if generated else [ARTIFACTS[0]] if retry_done else []
                    self.fulfill(
                        request_id,
                        {
                            "project_id": PROJECT,
                            "project_status": "page_plan_approved",
                            "provider_readiness": {
                                "configured": True,
                                "status": "ready",
                                "provider_id": "fake-local-creative",
                                "profile_id": IDENTITY["workflow_profile"],
                                "checkpoint": IDENTITY["checkpoint"],
                                "workflow_hash": IDENTITY["workflow_hash"],
                            },
                            "status": "review_ready" if generated else "failed" if retry_mode else "not_generated",
                            "operation_state":"remaining_samples_authorized" if retry_done else "retry_authorized" if retry_mode else "review_ready" if generated else "not_generated",
                            "selected_page_ids": IDENTITY["selected_page_ids"] if generated else [],
                            "retry_page_ids":["page-005","page-015"] if retry_done else ["page-001"] if retry_mode else [],
                            "retry_pages":[{"page_id":"page-005","title":"Campfire Teamwork Adventure 1"},{"page_id":"page-015","title":"Stargazing Adventure 1"}] if retry_done else [{"page_id":"page-001","title":"Arrival And Unpacking Adventure 1"}] if retry_mode else [],
                            "submitted_prompt_ids":["lost-prompt"] if retry_mode else [],
                            "artifacts": displayed_artifacts,
                            "approval": None,
                            "page_generation_policy":{"page_id":"page-001","profile_id":"kids-bold-line-art-v6","attempts_used":1,"maximum_attempts_per_page":3,"attempts_remaining":2,"generation_available":True,"new_prompt_revision":True,"blocked_reason":None},
                            "progress":{"operation_type":"regenerate_single_page" if self.mode=="single_regen_active" else "generate_samples","operation_state":progress_state,"active":progress_active,"generation_attempt_identity":"e"*64 if self.mode=="single_regen_active" else None,"prompt_revision":3 if self.mode=="single_regen_active" else None,"positive_prompt_hash":"c"*64 if self.mode=="single_regen_active" else None,"negative_prompt_hash":"d"*64 if self.mode=="single_regen_active" else None,"page_ids":["page-001"],"source_artifact_id":"candidate-newest","old_prompt_revision":2,"new_prompt_revision":3,"old_prompt_hash":"a"*64,"new_prompt_hash":"b"*64,"old_profile_id":"kids-bold-line-art-v6","new_profile_id":"kids-bold-line-art-v6","submitted_prompt_ids":["new-revision-3-prompt"] if self.mode=="single_regen_active" else ["active-prompt"] if progress_state=="provider_submitted" else [],"started_at":"2026-07-23T16:00:00-05:00","elapsed_seconds":42,"comfyui_instance_identity":{"instance_id":"fixture-instance","process_started_at":"fixture-start"},"queue_confirmation_state":"queue_confirmed" if progress_state=="provider_submitted" else "output_confirmed" if progress_state=="review_ready" else "not_submitted","provider_state_confirmed":progress_state in {"provider_submitted","review_ready"},"artifact_count":len(displayed_artifacts),"operation_artifact_count":1 if progress_state=="review_ready" else 0,"expected_artifact_count":1,"safe_failure_message":"simulated safe failure" if progress_state=="failed" else None,"last_status_update_at":"2026-07-23T16:00:42-05:00"},
                        },
                    )
                else:
                    self.send("Fetch.continueRequest", {"requestId": request_id})

    def wait_for_button(self):
        for _ in range(100):
            found = self.evaluate(
                "[...document.querySelectorAll('button')].some(b=>b.textContent==='Generate 3 Sample Pages')"
            )
            if found:
                return
            time.sleep(0.05)
        raise AssertionError("Generate button did not render")

    def finish_confirmed(self):
        request_id=self.confirmed_request_id
        if self.mode.startswith("http"):
            code=int(self.mode[4:]);self.fulfill(request_id,{"detail":f"simulated HTTP {code}"},code)
        elif self.mode=="rejected":
            self.fulfill(request_id,{"status":"rejected","message":"ComfyUI rejected the simulated prompt.",**IDENTITY,"artifacts":[]})
        else:
            self.fulfill(request_id,{"status":"review_ready",**IDENTITY,"artifacts":ARTIFACTS})

    def click(self):
        self.evaluate(
            "[...document.querySelectorAll('button')].find(b=>b.textContent==='Generate 3 Sample Pages').click()"
        )

    def status(self):
        return self.evaluate("document.getElementById('coloring-book-status').textContent")

    def close(self):
        self.running = False
        try:
            self.ws.close()
        except Exception:
            pass
        self.chrome.terminate()
        self.chrome.wait(timeout=5)
        try:
            self.profile.cleanup()
        except OSError:
            pass


def run(mode):
    browser = Browser(mode)
    try:
        browser.wait_for_button()
        if mode == "javascript":
            browser.evaluate("window.confirm=()=>{throw new Error('simulated browser exception')}")
        else:
            browser.evaluate("(()=>{window.__sampleStatusAtConfirmed='';const status=document.getElementById('coloring-book-status');new MutationObserver(()=>{if(status.textContent==='Generating 3 sample pages locally…')window.__sampleStatusAtConfirmed=status.textContent}).observe(status,{childList:true,subtree:true,characterData:true})})()")
        browser.click()
        if mode == "cancel":
            time.sleep(0.5)
            assert len(browser.preview_bodies) == 1
            assert len(browser.confirmed_bodies) == 0
            assert len(browser.dialogs) == 1
            assert "canceled" in browser.status()
        elif mode == "javascript":
            time.sleep(0.5)
            assert len(browser.preview_bodies) == 1
            assert len(browser.confirmed_bodies) == 0
            assert "JavaScript failure" in browser.status()
            assert "simulated browser exception" in browser.status()
        else:
            assert browser.confirmed_paused.wait(5)
            disabled = browser.evaluate(
                "window.__sampleStatusAtConfirmed"
            )
            assert disabled == "Generating 3 sample pages locally…", disabled
            assert len(browser.confirmed_bodies) == 1
            assert browser.confirmed_bodies[0] == {"csrf_token": browser.confirmed_bodies[0]["csrf_token"], "confirmed": True, **IDENTITY}
            time.sleep(0.8)
            if mode == "success":
                for _ in range(100):
                    if browser.sample_gets >= 2:
                        break
                    time.sleep(.05)
                assert browser.sample_gets >= 2
                assert browser.status() == "review_ready: 3 sample artifacts ready for review."
            elif mode == "rejected":
                assert "rejected" in browser.status()
                assert "ComfyUI rejected" in browser.status()
            elif mode == "network":
                assert "uncertain" in browser.status()
                assert "Do not retry automatically" in browser.status()
            else:
                code = mode[4:]
                assert f"HTTP {code}" in browser.status()
        return {
            "mode": mode,
            "preview": len(browser.preview_bodies),
            "confirmed": len(browser.confirmed_bodies),
            "dialogs": len(browser.dialogs),
            "sample_gets": browser.sample_gets,
            "status": browser.status(),
        }
    finally:
        browser.close()


def run_retry(mode,accept=True):
    browser=Browser(mode)
    try:
        for _ in range(100):
            visible=browser.evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Retry Unfinished Sample Page')")
            if visible:break
            time.sleep(.05)
        assert visible
        browser.evaluate("(()=>{window.__retryDisabled=false;const b=[...document.querySelectorAll('button')].find(x=>x.textContent==='Retry Unfinished Sample Page');new MutationObserver(()=>{if(b.disabled)window.__retryDisabled=true}).observe(b,{attributes:true,attributeFilter:['disabled']})})()")
        if not accept:
            browser.mode="cancel"
        else:
            browser.evaluate("setTimeout(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Retry Unfinished Sample Page')?.click(),50)")
        browser.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Retry Unfinished Sample Page').click()")
        time.sleep(.8)
        if not accept:
            assert len(browser.retry_preview_bodies)==1;assert len(browser.retry_confirmed_bodies)==0;assert "canceled" in browser.status()
        else:
            assert len(browser.retry_preview_bodies)==1;assert len(browser.retry_confirmed_bodies)==1;assert browser.evaluate("window.__retryDisabled") is True
            if mode!="retry_success":assert "HTTP 502" in browser.status()
        return {"mode":mode if accept else "retry_cancel","preview":len(browser.retry_preview_bodies),"confirmed":len(browser.retry_confirmed_bodies),"disabled":browser.evaluate("window.__retryDisabled"),"status":browser.status()}
    finally:browser.close()


def run_progress(mode):
    browser=Browser(mode)
    try:
        browser.evaluate(f"renderProducerProject('{PROJECT}')")
        for _ in range(100):
            if browser.evaluate("document.querySelector('[data-tab=\"samples\"]')!==null"):
                browser.evaluate("document.querySelector('[data-tab=\"samples\"]').click()")
                break
            time.sleep(.05)
        for _ in range(200):
            visible=browser.evaluate("document.body.innerText.includes('Sample Generation Status')")
            if visible:break
            time.sleep(.05)
        assert visible
        if mode=="progress_active":
            assert browser.evaluate("document.body.innerText.includes('Submitted to ComfyUI…')")
            assert browser.evaluate("document.body.innerText.includes('page-001')")
            assert browser.evaluate("document.body.innerText.includes('active-prompt')")
            assert browser.evaluate("[...document.querySelectorAll('[data-workspace-tab=\"samples\"] button')].filter(b=>/Generate|Regenerate/.test(b.textContent)).every(b=>b.disabled)")
            before=browser.sample_gets;browser.send("Page.reload")
            time.sleep(.8)
            browser.evaluate(f"renderProducerProject('{PROJECT}')");time.sleep(.5)
            assert browser.evaluate("document.body.innerText.includes('Submitted to ComfyUI…')")
            assert browser.sample_gets>before
            browser.progress_state="review_ready";time.sleep(3.4)
            assert browser.evaluate("document.body.innerText.includes('Ready for review')")
        elif mode=="progress_failure":
            assert browser.evaluate("document.body.innerText.includes('Failed safely')")
            assert browser.evaluate("document.body.innerText.includes('simulated safe failure')")
        elif mode=="progress_retry":
            assert browser.evaluate("document.body.innerText.includes('Retry authorization required')")
        else:
            assert browser.evaluate("document.body.innerText.includes('Ready for review')")
        assert browser.evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Refresh Status')")
        return {"mode":mode,"sample_gets":browser.sample_gets,"state":browser.evaluate("document.querySelector('.sample-generation-status').dataset.operationState")}
    finally:browser.close()


def run_validation_gate():
    browser=Browser("validation_invalid")
    try:
        browser.evaluate(f"renderProducerProject('{PROJECT}')");time.sleep(.5)
        for _ in range(100):
            if browser.evaluate("document.querySelector('[data-tab=\"samples\"]')!==null"):
                browser.evaluate("document.querySelector('[data-tab=\"samples\"]').click()");break
            time.sleep(.05)
        assert browser.evaluate("[...document.getElementById('coloring-book-project').querySelectorAll('button')].find(b=>b.textContent==='Approve').disabled")
        return {"mode":"validation_invalid","approve_disabled":True}
    finally:browser.close()


def run_single_regeneration_visibility():
    browser=Browser("single_regen_active")
    try:
        browser.evaluate("window.__scrolls=0;Element.prototype.scrollIntoView=function(){window.__scrolls++}")
        browser.evaluate(f"renderProducerProject('{PROJECT}')");time.sleep(.6)
        for _ in range(100):
            if browser.evaluate("document.querySelector('[data-tab=\"samples\"]')!==null"):
                browser.evaluate("document.querySelector('[data-tab=\"samples\"]').click()");break
            time.sleep(.05)
        assert browser.evaluate("document.body.innerText.includes('regenerate_single_page')")
        assert browser.evaluate("document.querySelector('.active-sample-candidate')!==null")
        assert browser.evaluate("document.querySelector('.sample-candidate-history').open===false")
        assert browser.evaluate("document.body.innerText.includes('Attempts: 1 of 3')")
        assert browser.evaluate("[...document.querySelectorAll('.active-sample-candidate button')].some(b=>b.textContent==='Regenerate page-001 with updated prompt'&&b.disabled)")
        assert browser.evaluate("document.querySelector('.sample-candidate-history pre')===null")
        assert not browser.evaluate("document.body.innerText.includes('New page-001 candidate ready for review.')")
        before=browser.sample_gets;browser.send("Page.reload");time.sleep(.8);browser.evaluate(f"renderProducerProject('{PROJECT}')");time.sleep(.8);assert browser.sample_gets>before
        browser.progress_state="review_ready";time.sleep(3.4)
        assert browser.evaluate("document.body.innerText.includes('New page-001 candidate ready for review.')")
        assert browser.evaluate("document.querySelector('.active-sample-candidate.newest-candidate-highlight')!==null")
        assert browser.evaluate("document.body.innerText.includes('new-revision-3-prompt')")
        return {"mode":"single_regeneration_visibility","sample_gets":browser.sample_gets,"history_collapsed":True,"newest_highlighted":True}
    finally:browser.close()


if __name__ == "__main__":
    results = [run(mode) for mode in ("cancel", "success", "rejected", "http403", "http409", "http422", "http500", "network", "javascript")]
    results += [run_retry("retry_success",False),run_retry("retry_success"),run_retry("retry_failure")]
    results += [run_progress(mode) for mode in ("progress_active","progress_completion","progress_failure","progress_retry")]
    results.append(run_validation_gate())
    results.append(run_single_regeneration_visibility())
    print(json.dumps(results, indent=2))
