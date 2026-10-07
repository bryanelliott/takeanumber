"""Exercise the real Bash startup barrier without touching a production database."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Linux startup script")
@pytest.mark.parametrize(
    "production, url, driver_status, migration_status, starts",
    [
        ("production", "test-secret-url", 0, 0, True),
        ("production", "test-secret-url", 0, 1, False),
        ("production", "test-secret-url", 1, 0, False),
        ("production", "", 0, 0, False),
        ("development", "test-secret-url", 0, 0, False),
    ],
)
def test_startup_requires_settings_driver_and_successful_migration(
    tmp_path, production, url, driver_status, migration_status, starts
):
    calls = tmp_path / "calls"
    python = tmp_path / "python"
    python.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "-c" ]; then exit "$DRIVER_STATUS"; fi\n'
        'test "$FLASK_SKIP_DOTENV" = "1" || exit 99\n'
        'printf "%s\\n" "$*" >> "$CALLS"\n'
        'exit "$MIGRATION_STATUS"\n'
    )
    gunicorn = tmp_path / "gunicorn"
    gunicorn.write_text('#!/bin/bash\nprintf "gunicorn %s\\n" "$*" >> "$CALLS"\n')
    python.chmod(0o700)
    gunicorn.chmod(0o700)
    result = subprocess.run(
        ["bash", str(ROOT / "startup.sh")],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "APP_ENV": production,
            "DATABASE_URL": url,
            "DRIVER_STATUS": str(driver_status),
            "MIGRATION_STATUS": str(migration_status),
            "CALLS": str(calls),
        },
        text=True,
        capture_output=True,
        timeout=10,
    )
    recorded = calls.read_text().splitlines() if calls.exists() else []
    assert (result.returncode == 0) is starts
    assert any(line.startswith("gunicorn ") for line in recorded) is starts
    if starts:
        assert recorded[0] == "-m flask --app app:create_app deploy-upgrade"
        assert "--workers 1" in recorded[1]
    assert "test-secret-url" not in result.stdout + result.stderr


def test_release_workflow_never_requires_a_production_database_connection():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
    assert "needs: verify" in workflow
    assert "environment: production" in workflow
    assert "azure/webapps-deploy@v3" in workflow
    assert "secrets.AZURE_WEBAPP_PUBLISH_PROFILE" in workflow
    for forbidden in (
        "DATABASE_URL",
        "azure/login",
        "migration_mode",
        "migrated_sha",
        "deploy-upgrade",
    ):
        assert forbidden not in workflow
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "docker compose up -d --wait test-db" in ci
    assert "docker compose run --rm test-runner" in ci
