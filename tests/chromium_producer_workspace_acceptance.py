#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import urllib.request
from contextlib import closing
from socket import socket

import websocket


BASE = "http://127.0.0.1:8787"
PROJECT = "book-project-20260719T224438-d0cba878"


def free_port() -> int:
    with closing(socket()) as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


class Browser:
    def __init__(self, width: int, height: int):
        self.port = free_port()
        self.profile = tempfile.TemporaryDirectory()
        self.process = subprocess.Popen(
            [
                "google-chrome",
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={self.profile.name}",
                f"{BASE}/app?view=agency.coloring-book-producer&project_id={PROJECT}&producer_tab=plan",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(120):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                tab = next(item for item in tabs if item.get("url", "").startswith(BASE))
                break
            except Exception:
                time.sleep(0.05)
        self.ws = websocket.create_connection(tab["webSocketDebuggerUrl"])
        self.serial = 0
        self.ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        self.ws.recv()
        self.ws.send(
            json.dumps(
                {
                    "id": 2,
                    "method": "Emulation.setDeviceMetricsOverride",
                    "params": {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                }
            )
        )
        self.ws.recv()

    def evaluate(self, expression: str):
        self.serial += 1
        call_id = 100 + self.serial
        self.ws.send(
            json.dumps(
                {
                    "id": call_id,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expression, "returnByValue": True},
                }
            )
        )
        while True:
            result = json.loads(self.ws.recv())
            if result.get("id") == call_id:
                return result["result"]["result"].get("value")

    def close(self):
        self.ws.close()
        self.process.terminate()
        self.process.wait(timeout=5)
        self.profile.cleanup()


def wait_until(browser: Browser, expression: str):
    for _ in range(300):
        if browser.evaluate(expression):
            return
        time.sleep(0.1)
    raise AssertionError(expression)


def run(width: int, height: int) -> dict:
    browser = Browser(width, height)
    try:
        wait_until(browser, "document.querySelector('.producer-workspace-tabs')!==null")
        wait_until(browser, "document.querySelectorAll('.compact-page-table tbody tr').length===10")
        assert browser.evaluate("document.querySelectorAll('.selected-page-editor').length===1")
        assert browser.evaluate("document.querySelectorAll('[data-workspace-tab=\"plan\"] article.agent-card').length===1")
        assert browser.evaluate("document.documentElement.scrollWidth<=document.documentElement.clientWidth")
        browser.evaluate("document.querySelector('[data-tab=\"samples\"]').click()")
        wait_until(browser, "document.querySelector('.active-sample-candidate')!==null")
        assert browser.evaluate("document.querySelector('.reference-sample-candidate')!==null")
        assert browser.evaluate("document.querySelector('.sample-candidate-history').open===false")
        assert browser.evaluate("[...document.querySelectorAll('.sample-candidate-history img')].every(x=>x.loading==='lazy')")
        assert browser.evaluate("document.querySelector('.sample-candidate-history pre')===null")
        assert browser.evaluate("document.querySelector('.active-sample-candidate button').textContent.length>0")
        assert browser.evaluate("new URLSearchParams(location.search).get('producer_tab')==='samples'")
        browser.evaluate("location.reload()")
        wait_until(browser, "document.querySelector('.producer-workspace-tabs')!==null")
        wait_until(browser, "[...document.querySelectorAll('[data-workspace-tab=\"samples\"]')].some(x=>!x.hidden)")
        assert browser.evaluate("document.documentElement.scrollWidth<=document.documentElement.clientWidth")
        return {
            "viewport": f"{width}x{height}",
            "page_rows": browser.evaluate("document.querySelectorAll('.compact-page-table tbody tr').length"),
            "page_editors": browser.evaluate("document.querySelectorAll('.selected-page-editor').length"),
            "history_collapsed": True,
            "horizontal_overflow": False,
        }
    finally:
        browser.close()


if __name__ == "__main__":
    print(json.dumps([run(1920, 1080), run(1366, 768)], indent=2))
