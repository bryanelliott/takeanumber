"""Optional real-DOM checks; core Socket.IO tests require no browser installation."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "fixture_name",
    [
        "browser_live_updates.html",
        "browser_student_alerts.html",
        "browser_student_alerts.html#unsupported",
        "browser_student_alerts.html#blocked",
    ],
)
def test_live_browser_behavior(tmp_path, fixture_name):
    candidates = [
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    browser = next((path for path in candidates if path and Path(path).is_file()), None)
    if browser is None:
        pytest.skip("Chrome/Chromium/Edge is not installed for optional DOM checks")
    filename, _, fragment = fixture_name.partition("#")
    fixture = Path(__file__).with_name(filename).resolve().as_uri()
    if fragment:
        fixture += "#" + fragment
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
