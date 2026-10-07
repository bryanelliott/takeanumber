from unittest.mock import patch

import pytest

from app import create_app
from app.extensions import db

TEST_URL = "mssql+pyodbc://user_test:password@127.0.0.1:55433/example_test?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
DEV_URL = "mssql+pyodbc://user_dev:password@127.0.0.1:55432/example_dev?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"


@pytest.fixture
def config():
    return {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "TEST_DATABASE_URL": TEST_URL,
        "DATABASE_URL": DEV_URL,
    }


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "invalid-password-secret",
        "sqlite:///:memory:",
        "mysql://user:password@localhost/example_test",
        "mssql+pyodbc://user_test:password@localhost:invalid/example_test",
        "mssql+pyodbc://user_test:password@localhost:99999/example_test",
        "mssql+pyodbc:///example_test",
        DEV_URL,
        TEST_URL.replace("example_test", "example_dev"),
        TEST_URL.replace("user_test", "user_dev"),
        TEST_URL.replace("127.0.0.1", "remote.example"),
        TEST_URL + "&dbname=example_dev",
        TEST_URL + "&host=remote.example",
        TEST_URL + "&service=production",
        TEST_URL.replace("Encrypt=yes", "Encrypt=no"),
        TEST_URL.replace("Driver+18", "Driver+17"),
        TEST_URL + "&TrustServerCertificate=no",
        TEST_URL + "&Authentication=ActiveDirectoryDefault",
        TEST_URL.replace("127.0.0.1", "127.0.0.1%3BDATABASE%3Dother"),
    ],
)
def test_unsafe_test_configuration_fails_before_engine_initialization(config, url):
    config["TEST_DATABASE_URL"] = url
    with patch.object(db, "init_app") as initialize:
        with pytest.raises(ValueError) as error:
            create_app(config)
        initialize.assert_not_called()
    assert "invalid-password-secret" not in str(error.value)
    assert "user_test:password" not in str(error.value)


def test_test_database_cannot_match_development_database(config):
    config["DATABASE_URL"] = TEST_URL.replace("55433", "55432")
    with pytest.raises(ValueError, match="names must differ"):
        create_app(config)


@pytest.mark.parametrize("url", [None, "sqlite:///:memory:"])
def test_ordinary_app_requires_sqlserver(config, url):
    config.update(TESTING=False, DATABASE_URL=url)
    with patch.object(db, "init_app") as initialize:
        with pytest.raises(ValueError):
            create_app(config)
        initialize.assert_not_called()


def test_binds_cannot_bypass_database_selection(config):
    config["SQLALCHEMY_BINDS"] = {"other": DEV_URL}
    with pytest.raises(ValueError, match="binds"):
        create_app(config)


def test_uri_override_cannot_select_development_database(config):
    config["SQLALCHEMY_DATABASE_URI"] = DEV_URL
    application = create_app(config)
    with application.app_context():
        assert db.engine.url.database == "example_test"
        db.engine.dispose()


def test_environment_is_read_for_each_factory_call(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("DATABASE_URL", DEV_URL)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    first = create_app({"TESTING": True})
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL.replace("example_test", "second_test"))
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    second = create_app({"TESTING": True})
    assert first.config["SESSION_COOKIE_SECURE"] is False
    assert second.config["SESSION_COOKIE_SECURE"] is True
    for application, expected in [(first, "example_test"), (second, "second_test")]:
        with application.app_context():
            assert db.engine.url.database == expected
            db.engine.dispose()


def test_other_driver_cannot_bypass_security_options(config):
    config["TEST_DATABASE_URL"] = TEST_URL.replace("mssql+pyodbc", "mssql+pymssql")
    with pytest.raises(ValueError, match="pyodbc"):
        create_app(config)


def test_secret_key_required(config):
    config["SECRET_KEY"] = ""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app(config)


def test_invalid_cookie_boolean_rejected(config, monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "not-a-boolean")
    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        create_app(config)
