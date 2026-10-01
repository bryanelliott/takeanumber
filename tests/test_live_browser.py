"""Optional real-DOM checks; core Socket.IO tests require no browser installation."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_live_update_dom_reconnect_ordering_and_drafts(tmp_path):
    candidates = [
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    browser = next((path for path in candidates if path and Path(path).is_file()), None)
    if browser is None:
        pytest.skip("Chrome/Chromium/Edge is not installed for optional DOM checks")
    fixture = Path(__file__).with_name("browser_live_updates.html").resolve().as_uri()
    result = subprocess.run(
        [
            browser,
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-extensions",
            f"--user-data-dir={tmp_path / 'browser-profile'}",
            "--virtual-time-budget=5000",
            "--dump-dom",
            fixture,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stderr
    assert 'data-result="passed"' in result.stdout, result.stdout + result.stderr
