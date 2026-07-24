"""Chromium acceptance for the durable global activity shell indicator."""
from __future__ import annotations
import base64
import json
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import websocket

BASE = "http://127.0.0.1:8787"
PROJECT = "book-project-20260719T224438-d0cba878"


class Browser:
    def __init__(self):
        self.state = "Working"
        self.serial = 0
        self.responses = {}
        self.running = True
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0)); self.port = probe.getsockname()[1]
        self.profile = tempfile.TemporaryDirectory()
        self.chrome = subprocess.Popen(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
            f"--remote-debugging-port={self.port}", "--remote-allow-origins=*",
            f"--user-data-dir={self.profile.name}", f"{BASE}/app?view=dashboard"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                tab = next(x for x in tabs if x.get("url", "").startswith(BASE)); break
            except Exception: time.sleep(.05)
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"])
        threading.Thread(target=self.reader, daemon=True).start()
        self.send("Runtime.enable")
        self.send("Fetch.enable", {"patterns": [{"urlPattern": "*/app/activity-status*", "requestStage": "Request"}]})

    def send(self, method, params=None):
        self.serial += 1
        self.ws.send(json.dumps({"id": self.serial, "method": method, "params": params or {}}))
        return self.serial

    def eval(self, expression):
        cid = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        for _ in range(150):
            if cid in self.responses:
                return self.responses.pop(cid)["result"]["result"].get("value")
            time.sleep(.02)
        raise AssertionError(expression)

    def payload(self):
        state = self.state
        if state == "Idle":
            return {"state": "Idle", "display_label": "Idle", "items": [], "has_unresolved_activity": False, "poll_interval_ms": 15000}
        labels = {"Working": "Generating page-001", "Waiting for approval": "Preparing Printify draft",
            "Failed": "Sample generation"}
        item = {"state": state, "display_label": labels[state], "operation_type": "generate_samples",
            "agent_capability_id": "jamesos.coloring-book-producer", "project_id": PROJECT, "job_id": None,
            "workspace_url": f"/app?view=agency.coloring-book-producer&project_id={PROJECT}",
            "operation_state": "running" if state == "Working" else "awaiting_human_approval" if state == "Waiting for approval" else "failed",
            "started_timestamp": "2026-07-23T17:00:00+00:00", "elapsed_seconds": 42,
            "progress_current": 0, "progress_expected": 1, "approval_required": state == "Waiting for approval",
            "safe_failure_message": "Simulated safe failure." if state == "Failed" else None,
            "last_update_timestamp": "2026-07-23T17:00:42+00:00"}
        display = f"Working: {labels[state]}" if state == "Working" else state
        return {"state": state, "display_label": display, "items": [item],
            "has_unresolved_activity": True, "poll_interval_ms": 3000}

    def reader(self):
        while self.running:
            try: value = json.loads(self.ws.recv())
            except Exception: return
            if "id" in value:
                self.responses[value["id"]] = value; continue
            if value.get("method") == "Fetch.requestPaused":
                body = base64.b64encode(json.dumps(self.payload()).encode()).decode()
                self.send("Fetch.fulfillRequest", {"requestId": value["params"]["requestId"], "responseCode": 200,
                    "responseHeaders": [{"name": "Content-Type", "value": "application/json"}], "body": body})

    def refresh_activity(self):
        self.eval("fetch('/app/activity-status',{cache:'no-store'}).then(r=>r.json()).then(renderGlobalActivity)")
        for _ in range(200):
            if self.eval("document.querySelector('#global-activity-indicator')?.dataset.state") == self.state:
                return
            time.sleep(.03)
        raise AssertionError(f"activity did not become {self.state}")

    def close(self):
        self.running = False
        try: self.ws.close()
        finally:
            self.chrome.terminate(); self.chrome.wait(timeout=5); self.profile.cleanup()


def browser_for(state):
    browser = Browser(); browser.state = state
    browser.eval("fetch('/app/activity-status',{cache:'no-store'}).then(r=>r.json()).then(renderGlobalActivity)")
    for _ in range(150):
        if browser.eval("document.querySelector('#global-activity-indicator')?.dataset.state") == state:
            return browser
        time.sleep(.03)
    browser.close(); raise AssertionError(state)


def main():
    browser = browser_for("Working")
    try:
        assert browser.eval("document.querySelector('#health-dot')!==null")
        assert browser.eval("document.querySelector('#global-activity-indicator')?.previousElementSibling?.id") == "health-dot"
        assert browser.eval("document.querySelector('#global-activity-label')?.textContent") == "Working: Generating page-001"
        browser.eval("document.querySelector('#global-activity-indicator').click()")
        assert browser.eval("document.querySelector('#global-activity-panel').hidden") is False
        assert browser.eval("document.querySelector('[data-workspace-url]')?.dataset.workspaceUrl") == f"/app?view=agency.coloring-book-producer&project_id={PROJECT}"
    finally: browser.close()
    browser = browser_for("Idle")
    try: assert browser.eval("document.querySelector('#global-activity-label').textContent") == "Idle"
    finally: browser.close()
    browser = browser_for("Waiting for approval")
    try: assert browser.eval("document.querySelector('#global-activity-label').textContent") == "Waiting for approval"
    finally: browser.close()
    browser = browser_for("Failed")
    try:
        assert browser.eval("document.querySelector('#global-activity-items').textContent.includes('Simulated safe failure.')")
        assert browser.eval("document.querySelector('#global-activity-indicator').getAttribute('aria-label')") == "Global activity: Failed"
    finally: browser.close()
    print("Chromium activity acceptance passed: adjacent indicator, Working, Idle, approval, failure, panel, canonical workspace.")


if __name__ == "__main__":
    main()
