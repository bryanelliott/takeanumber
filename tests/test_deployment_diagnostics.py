import socket
import ssl
from unittest.mock import patch

import click
import psycopg
import pytest
from alembic.util.exc import CommandError
from sqlalchemy.exc import OperationalError

from app.extensions import db

SECRET = "sentinel-password-and-student-data"


@pytest.mark.parametrize("command", ["check-db", "deploy-upgrade"])
@pytest.mark.parametrize(
    "error,category",
    [
        (socket.gaierror(SECRET), "dns-resolution"),
        (psycopg.OperationalError("could not translate host name " + SECRET), "dns-resolution"),
        (psycopg.OperationalError("Name or service not known " + SECRET), "dns-resolution"),
        (TimeoutError(SECRET), "network-timeout"),
        (psycopg.errors.ConnectionTimeout(SECRET), "network-timeout"),
        (psycopg.OperationalError("connection timed out " + SECRET), "network-timeout"),
        (ssl.SSLCertVerificationError(SECRET), "tls-verification"),
        (
            psycopg.OperationalError("SSL error: certificate verify failed " + SECRET),
            "tls-verification",
        ),
        (
            psycopg.OperationalError("root certificate file does not exist " + SECRET),
            "tls-verification",
        ),
        (
            psycopg.OperationalError("server certificate does not match host name " + SECRET),
            "tls-verification",
        ),
        (psycopg.errors.InvalidPassword(SECRET), "postgres-authentication"),
        (
            psycopg.OperationalError("password authentication failed " + SECRET),
            "postgres-authentication",
        ),
        (psycopg.errors.InsufficientPrivilege(SECRET), "database-privileges"),
        (
            psycopg.OperationalError("permission denied for database " + SECRET),
            "database-privileges",
        ),
        (psycopg.OperationalError("no pg_hba.conf entry " + SECRET), "network-access-policy"),
        (psycopg.OperationalError("connection refused " + SECRET), "database-connection"),
    ],
)
def test_connection_errors_are_categorized_without_secrets(app, command, error, category, caplog):
    # Include sensitive SQL and bound parameters in the SQLAlchemy wrapper too.
    wrapped = OperationalError(f"SELECT '{SECRET}'", {"password": SECRET}, error)
    method = "connect" if command == "check-db" else "begin"
    with app.app_context(), patch.object(db.engine, method, side_effect=wrapped):
        result = app.test_cli_runner().invoke(args=[command])
    assert result.exit_code != 0
    assert f"[{category}]" in result.output
    assert SECRET not in result.output + caplog.text
    assert "SELECT" not in result.output


@pytest.mark.parametrize(
    "error,category",
    [
        (psycopg.errors.InsufficientPrivilege(SECRET), "database-privileges"),
        (psycopg.errors.LockNotAvailable(SECRET), "migration-timeout"),
        (psycopg.errors.QueryCanceled(SECRET), "migration-timeout"),
        (CommandError(SECRET), "alembic-migration"),
        (click.ClickException(SECRET), "alembic-migration"),
    ],
)
def test_migration_errors_are_sanitized_and_release_lock(app, auth_db, error, category, caplog):
    with patch("app.cli.command.upgrade", side_effect=error):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code != 0
    assert f"[{category}]" in result.output
    assert SECRET not in result.output + caplog.text
    assert app.test_cli_runner().invoke(args=["deploy-upgrade"]).exit_code == 0


def test_release_revision_loading_errors_are_sanitized(app, caplog):
    with patch("app.cli.ScriptDirectory.from_config", side_effect=CommandError(SECRET)):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code != 0
    assert "[alembic-migration]" in result.output
    assert SECRET not in result.output + caplog.text
