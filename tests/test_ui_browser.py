"""Optional full-template Chrome QA. Synthetic snapshots; never opens a database.

Set UI_QA_ARTIFACT_DIR to export screenshots and measured DOM/resource reports.
Uses existing simple-websocket/CDP, not a production browser dependency.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import urlopen
from uuid import uuid4
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest
from flask import session
from simple_websocket import Client

from app import create_app
from app.services.queue import ClientState, MasterEntry, MasterState
from app.services.sessions import SessionNotFound
from app.services.settings import AlertPreferences

pytestmark = pytest.mark.browser
VIEWPORTS = [
    (320, 568),
    (375, 667),
    (390, 844),
    (430, 932),
    (768, 1024),
    (1024, 768),
    (1280, 800),
    (1440, 900),
    (1920, 1080),
    (2560, 1440),
]
AUDIT = Path(__file__).with_name("ui_audit.js").read_text(encoding="utf-8")


class Chrome:
    def __init__(self, executable, profile):
        arguments = [
            executable,
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-extensions",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ]
        if sys.platform == "linux" and (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
            arguments.insert(1, "--no-sandbox")
        self.process = subprocess.Popen(
            arguments,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.ws = None
        try:
            deadline = time.monotonic() + 15
            while not (profile / "DevToolsActivePort").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("Chrome debugging port did not start")
                time.sleep(0.05)
            port = (profile / "DevToolsActivePort").read_text().splitlines()[0]
            with urlopen(f"http://127.0.0.1:{port}/json", timeout=10) as response:
                tabs = json.load(response)
            self.ws = Client.connect(
                next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
            )
            self.counter = 0
            self.exceptions = []
            self.call("Page.enable")
            self.call("Runtime.enable")
            self.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
              window.__qaCls = 0;
              new PerformanceObserver(list => list.getEntries().forEach(e => {
                if (!e.hadRecentInput) window.__qaCls += e.value;
              })).observe({type: 'layout-shift', buffered: true});
              window.__qaSocket = {handlers: {}, connected: true, active: true,
                on(name, fn) {this.handlers[name] = fn;},
                connect() {setTimeout(() => this.handlers.connect?.(), 0);},
                disconnect() {this.connected = false;}};
              Object.defineProperty(window, 'io', {
                get: () => () => window.__qaSocket, set() {}
              });
            """
                },
            )
        except Exception:
            self.close()
            raise

    def call(self, method, parameters=None):
        self.counter += 1
        self.ws.send(json.dumps({"id": self.counter, "method": method, "params": parameters or {}}))
        while True:
            message = json.loads(self.ws.receive(timeout=15))
            if message.get("method") == "Runtime.exceptionThrown":
                self.exceptions.append(message["params"]["exceptionDetails"])
            if message.get("id") == self.counter:
                assert "error" not in message, message
                return message.get("result", {})

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        assert "exceptionDetails" not in result, result
        return result["result"].get("value")

    def navigate(self, url, *, scripts=True):
        self.call("Page.navigate", {"url": url})
        time.sleep(0.06)
        for _ in range(100):
            if self.evaluate("document.readyState === 'complete'"):
                break
            time.sleep(0.02)
        else:
            raise TimeoutError("Document did not finish loading")
        self.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")
        if scripts:
            self.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    def viewport(self, width, height, scale=1):
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": scale, "mobile": False},
        )

    def key(self, key, code=None):
        self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code or key})
        self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code or key})

    def screenshot(self, path):
        result = self.call("Page.captureScreenshot", {"format": "png"})
        path.write_bytes(base64.b64decode(result["data"]))

    def close(self):
        if self.ws:
            try:
                self.call("Browser.close")
            except Exception:
                pass
            self.ws.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)


@pytest.fixture(scope="module")
def rendered_app(tmp_path_factory):
    candidates = [
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    executable = next((p for p in candidates if p and Path(p).is_file()), None)
    if executable is None:
        pytest.skip("Chrome/Chromium/Edge unavailable for optional template QA")
    application = create_app(
        {
            "TESTING": True,
            "APP_ENV": "development",
            "SECRET_KEY": "template-qa-only",
            "DATABASE_URL": None,
            "TRUSTED_HOSTS": ["127.0.0.1"],
            "SESSION_COOKIE_SECURE": False,
            "AUTH_RATE_LIMIT": 10000,
            "TEST_DATABASE_URL": "mssql+pyodbc://visual_test:unused@127.0.0.1/visual_test"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            "&Encrypt=yes&TrustServerCertificate=yes",
        }
    )
    owner = SimpleNamespace(
        id=uuid4(),
        display_name="Instructor Morgan",
        is_active=True,
        is_authenticated=True,
        is_anonymous=False,
    )
    now = datetime.now(UTC)
    entries = tuple(
        MasterEntry(uuid4(), n, name)
        for n, name in [(24, "Alex Morgan"), (25, "Jordan Lee"), (26, None)]
    )
    model = SimpleNamespace(
        authenticated=False,
        active=None,
        owner=owner,
        application=application,
        master=MasterState("qa-session", "active", now, None, entries[0], entries[1:], 2),
        client=ClientState("qa-session", owner.display_name, "not_joined"),
    )
    application.login_manager.user_loader(lambda _: owner)

    @application.before_request
    def synthetic_login():
        if model.authenticated:
            session["_user_id"] = str(owner.id)
            session["_fresh"] = True
        else:
            session.pop("_user_id", None)

    def client_state(code, token):
        if code != "qa-session":
            raise SessionNotFound()
        return model.client

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    artifacts = Path(os.environ.get("UI_QA_ARTIFACT_DIR", tmp_path_factory.mktemp("ui-results")))
    artifacts.mkdir(parents=True, exist_ok=True)
    model.artifacts = artifacts
    with (
        patch("app.instructor.routes.queue.master_state", side_effect=lambda *args: model.master),
        patch(
            "app.instructor.routes.sessions.active_session", side_effect=lambda *args: model.active
        ),
        patch(
            "app.instructor.routes.sessions.owned_session",
            side_effect=lambda *args: SimpleNamespace(status=model.master.status),
        ),
        patch("app.instructor.routes.settings.get_preferences", return_value=AlertPreferences()),
        patch("app.queue.routes.queue.client_state", side_effect=client_state),
    ):
        server = make_server("127.0.0.1", 0, application, handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        browser = Chrome(executable, tmp_path_factory.mktemp("ui-chrome"))
        model.browser = browser
        model.origin = f"http://127.0.0.1:{server.server_port}"
        try:
            yield model
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def pages(model):
    model.authenticated = False
    yield "landing", "/", False
    yield "login", "/auth/login", False
    yield "signup", "/auth/signup", False
    model.authenticated = True
    yield "landing-authenticated", "/", False
    model.active = None
    yield "dashboard-empty", "/instructor/dashboard", False
    model.active = SimpleNamespace(public_code="qa-session")
    yield "dashboard-active", "/instructor/dashboard", False
    yield "settings", "/instructor/settings", False
    original = model.master
    for name, serving, waiting in [
        ("empty", None, ()),
        ("waiting", None, original.waiting),
        ("serving", original.serving, original.waiting),
    ]:
        model.master = replace(
            original, serving=serving, waiting=waiting, waiting_count=len(waiting)
        )
        yield f"master-{name}", "/instructor/sessions/qa-session/master", False
        yield f"presentation-{name}", "/instructor/sessions/qa-session/master", True
    model.master = replace(original, status="ended", ended_at=datetime.now(UTC))
    yield "master-ended", "/instructor/sessions/qa-session/master", False
    model.master = original
    model.authenticated = False
    for status, alert in [
        ("not_joined", None),
        ("waiting", None),
        ("waiting", "next_up"),
        ("waiting", "advance_warning"),
        ("serving", "serving"),
        ("completed", None),
        ("left", None),
        ("ended", None),
    ]:
        model.client = ClientState(
            "qa-session",
            model.owner.display_name,
            status,
            None if status == "not_joined" else "test-entry",
            24 if status != "not_joined" else None,
            "Alex Morgan",
            1 if alert == "next_up" else 2,
            8,
            alert,
            AlertPreferences(advance_warning_count=3),
        )
        yield f"client-{alert or status}", "/session/qa-session", False
    yield "client-exit", "/session/qa-session/exit", False
    yield "client-not-found", "/session/missing", False


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_all_viewports(rendered_app, width, height):
    model, errors, results = rendered_app, [], []
    browser = model.browser
    browser.viewport(width, height)
    for name, path, presenting in pages(model):
        browser.navigate(model.origin + path)
        if name.startswith(("master-", "presentation-")) and name != "master-ended":
            browser.evaluate("sessionStorage.clear()")
            if browser.evaluate("document.body.classList.contains('is-presenting')") != presenting:
                browser.evaluate("document.getElementById('presentation-toggle').click()")
        report = browser.evaluate(AUDIT)
        if report["scrollWidth"] > width:
            report["errors"].append("Horizontal overflow")
        if report["connection"] and report["connection"]["bottom"] > height:
            report["errors"].append("Connection feedback below fold")
        if report["qr"]:
            qr = report["qr"]
            if abs(qr["width"] - qr["height"]) > 1:
                report["errors"].append("QR distorted")
            if width >= 1024 and qr["left"] < width / 2 - 20:
                report["errors"].append("QR not in right half")
            if width >= 1920:
                if max(qr["bottom"], report["next"]["bottom"]) > height:
                    report["errors"].append("Primary classroom content below fold")
        if width in (320, 390, 1920):
            browser.screenshot(model.artifacts / f"{name}-{width}.png")
        errors.extend(f"{name}: {error}" for error in report["errors"])
        results.append({"page": name, **report})
    (model.artifacts / f"viewport-{width}.json").write_text(json.dumps(results, indent=2))
    assert not browser.exceptions, browser.exceptions
    assert not errors, errors


def test_reflow_spacing_and_keyboard(rendered_app):
    model, errors, results = rendered_app, [], []
    browser = model.browser
    browser.viewport(320, 568)
    for name, path, presenting in pages(model):
        if presenting or name == "landing-authenticated":
            continue
        browser.navigate(model.origin + path)
        browser.evaluate("sessionStorage.clear(); document.body.classList.remove('is-presenting')")
        browser.evaluate("""const spacing = document.createElement('style');
          spacing.textContent = '* {line-height:1.5 !important; letter-spacing:.12em !important;'
            + 'word-spacing:.16em !important;} p {margin-bottom:2em !important;}';
          document.head.append(spacing);
        """)
        report = browser.evaluate(AUDIT)
        if report["scrollWidth"] > 320:
            errors.append(f"{name}: text-spacing overflow {report['scrollWidth']}")
        results.append({"page": name, "spacing": report["scrollWidth"]})
        browser.navigate(model.origin + path)
        browser.evaluate("document.documentElement.style.fontSize = '200%'")
        if browser.evaluate("document.documentElement.scrollWidth > innerWidth"):
            errors.append(f"{name}: 200% text overflow")
            results.append(
                {
                    "page": name,
                    "overflow": browser.evaluate("""
              [...document.querySelectorAll('body *')].filter(n => {
                const r = n.getBoundingClientRect(); return r.width && r.right > innerWidth;
              }).map(n => ({tag: n.tagName, class: n.className,
                           width: n.getBoundingClientRect().width}))
            """),
                }
            )
            browser.screenshot(model.artifacts / f"{name}-text-200.png")
    (model.artifacts / "reflow.json").write_text(json.dumps(results, indent=2))
    model.authenticated = False
    browser.navigate(model.origin + "/auth/login")
    browser.key("Tab")
    assert browser.evaluate("document.activeElement.classList.contains('skip-link')")
    browser.key("Enter")
    assert browser.evaluate("document.activeElement.id === 'main-content'")
    browser.key("Tab")
    assert browser.evaluate("document.activeElement.id === 'email'")
    assert browser.evaluate("getComputedStyle(document.activeElement).outlineStyle !== 'none'")
    assert not errors, errors


@pytest.mark.parametrize("view", ["client", "master", "presentation"])
def test_network_recovery_and_no_script(rendered_app, view):
    model, browser = rendered_app, rendered_app.browser
    model.authenticated = view != "client"
    model.client = ClientState(
        "qa-session",
        model.owner.display_name,
        "waiting",
        "test-entry",
        24,
        "Alex Morgan",
        2,
        8,
    )
    path = "/session/qa-session" if view == "client" else "/instructor/sessions/qa-session/master"
    browser.viewport(390, 844) if view == "client" else browser.viewport(1920, 1080)
    browser.navigate(model.origin + path)
    for _ in range(250):
        if browser.evaluate(
            "document.getElementById('live-status').textContent === 'Live updates connected.'"
        ):
            break
        time.sleep(0.02)
    else:
        pytest.fail("Initial state read did not finish")
    browser.evaluate("sessionStorage.clear(); document.body.classList.remove('is-presenting')")
    if view == "presentation":
        browser.evaluate("document.getElementById('presentation-toggle').click()")
    browser.evaluate("window.__originalQr = document.querySelector('.qr')")
    browser.call("Network.enable")
    network = {"latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}
    try:
        browser.call("Network.emulateNetworkConditions", {"offline": True, **network})
        browser.evaluate("new Promise(r => setTimeout(r, 100))")
        assert browser.evaluate(
            "document.getElementById('live-status').textContent.includes('offline')"
        )
        report = browser.evaluate(AUDIT)
        assert not report["errors"], report["errors"]
        assert report["connection"]["bottom"] <= report["height"]
        if report["qr"]:
            assert max(report["qr"]["bottom"], report["next"]["bottom"]) <= report["height"]
        browser.screenshot(model.artifacts / f"{view}-offline.png")
        # Change only the synthetic snapshot; recovery must actually read it over HTTP.
        if view == "client":
            model.client = replace(model.client, status="completed")
        else:
            model.master = replace(
                model.master, serving=replace(model.master.serving, queue_number=81)
            )
        browser.call("Network.emulateNetworkConditions", {"offline": False, **network})
        for _ in range(250):
            if browser.evaluate(
                "document.getElementById('live-status').textContent === 'Live updates connected.'"
            ):
                break
            time.sleep(0.02)
        else:
            pytest.fail(
                "Online recovery did not refresh state: "
                + browser.evaluate("document.getElementById('live-status').textContent")
            )
        if view == "client":
            assert browser.evaluate(
                "document.querySelector('[data-client-status]')"
                ".dataset.clientStatus === 'completed'"
            )
        else:
            assert browser.evaluate(
                "document.querySelector('.ticket-number').textContent.includes('81')"
            )
            assert browser.evaluate("window.__originalQr === document.querySelector('.qr')")
        if view == "presentation":
            browser.key("Escape")
            assert browser.evaluate(
                "!document.body.classList.contains('is-presenting') && "
                "document.activeElement.id === 'presentation-toggle'"
            )
    finally:
        browser.call("Network.emulateNetworkConditions", {"offline": False, **network})
    browser.call("Emulation.setScriptExecutionDisabled", {"value": True})
    try:
        browser.navigate(model.origin + path, scripts=False)
        assert browser.evaluate("document.getElementById('live-status').hidden")
        assert browser.evaluate(
            "document.querySelector('noscript').innerText.includes('Refresh this page')"
        )
        assert browser.evaluate("!!document.querySelector('form input[name=csrf_token]')")
    finally:
        browser.call("Emulation.setScriptExecutionDisabled", {"value": False})
