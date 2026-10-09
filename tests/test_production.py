from unittest.mock import patch

import pytest
from flask import request, url_for

from app import create_app
from app.extensions import db

PRODUCTION_URL = (
    "mssql+pyodbc://runtime:password@server.database.windows.net/takeanumber"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


@pytest.fixture
def production_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    return {
        "APP_ENV": "production",
        "SECRET_KEY": "test-only-production-shaped-secret-12345",
        "DATABASE_URL": PRODUCTION_URL,
        "TESTING": False,
        "DEBUG": False,
        "SESSION_COOKIE_SECURE": True,
        "TRUSTED_HOSTS": ["queue.example.edu"],
        "PROXY_FIX_X_FOR": 0,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"APP_ENV": "unknown"},
        {"SECRET_KEY": "short"},
        {"SECRET_KEY": "replace-with-a-random-local-secret"},
        {"SESSION_COOKIE_SECURE": False},
        {"DEBUG": True},
        {"TESTING": True},
        {"TRUSTED_HOSTS": None},
        {"TRUSTED_HOSTS": [".example.edu"]},
        {"TRUSTED_HOSTS": ["https://queue.example.edu"]},
        {"DATABASE_URL": PRODUCTION_URL.replace("server.database.windows.net", "localhost")},
        {
            "DATABASE_URL": PRODUCTION_URL.replace(
                "TrustServerCertificate=no", "TrustServerCertificate=yes"
            )
        },
        {"DATABASE_URL": PRODUCTION_URL.split("&Encrypt")[0]},
        {"DATABASE_URL": PRODUCTION_URL + "&host=elsewhere.example"},
        {"DATABASE_URL": PRODUCTION_URL + "&odbc_connect=override"},
    ],
)
def test_production_rejects_unsafe_configuration_before_engine(production_config, overrides):
    with patch.object(db, "init_app") as initialize:
        with pytest.raises(ValueError) as error:
            create_app({**production_config, **overrides})
        initialize.assert_not_called()
    assert "runtime:password" not in str(error.value)


def test_production_rejects_debug_environment(production_config, monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    with pytest.raises(ValueError, match="debug"):
        create_app(production_config)


def test_production_proxy_scheme_hosts_and_secure_cookies(production_config):
    with patch("app.load_dotenv") as dotenv:
        app = create_app(production_config)
        dotenv.assert_not_called()

    @app.get("/proxy-check")
    def proxy_check():
        return {"url": url_for("health.health", _external=True), "remote": request.remote_addr}

    browser = app.test_client()
    headers = {
        "Host": "queue.example.edu",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "attacker.example",
        "X-Forwarded-For": "198.51.100.5",
    }
    result = browser.get("/proxy-check", headers=headers)
    assert result.json == {"url": "https://queue.example.edu/health", "remote": "127.0.0.1"}
    landing = browser.get("/", headers=headers)
    assert landing.status_code == 200 and "Less waiting." in landing.text
    page = browser.get("/auth/login", headers=headers)
    assert page.status_code == 200
    assert "Secure" in page.headers["Set-Cookie"] and "HttpOnly" in page.headers["Set-Cookie"]
    assert browser.get("/health", headers={"Host": "attacker.example"}).status_code == 400
    with app.app_context():
        assert db.engine.url.query["TrustServerCertificate"] == "no"
        db.engine.dispose()


def test_verified_proxy_client_address_is_opt_in(production_config):
    app = create_app({**production_config, "PROXY_FIX_X_FOR": 1})

    @app.get("/proxy-address")
    def proxy_address():
        return {"remote": request.remote_addr}

    response = app.test_client().get(
        "/proxy-address",
        headers={
            "Host": "queue.example.edu",
            "X-Forwarded-For": "forged, 198.51.100.5",
        },
    )
    assert response.json == {"remote": "198.51.100.5"}
    with app.app_context():
        db.engine.dispose()


@pytest.mark.parametrize("value", ["-1", "4", "yes"])
def test_invalid_proxy_trust_count_rejected(production_config, monkeypatch, value):
    monkeypatch.setenv("PROXY_FIX_X_FOR", value)
    with pytest.raises(ValueError, match="PROXY_FIX_X_FOR"):
        create_app(production_config)
