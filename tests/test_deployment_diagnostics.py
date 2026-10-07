import socket
import ssl
from unittest.mock import patch

import click
import pyodbc
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
        (pyodbc.OperationalError("08001", "host missing (11001) " + SECRET), "dns-resolution"),
        (TimeoutError(SECRET), "network-timeout"),
        (pyodbc.OperationalError("HYT00", SECRET), "network-timeout"),
        (ssl.SSLCertVerificationError(SECRET), "tls-verification"),
        (
            pyodbc.OperationalError("08001", "SSL Provider certificate failed " + SECRET),
            "tls-verification",
        ),
        (
            pyodbc.OperationalError("28000", "login failed (18456) " + SECRET),
            "database-authentication",
        ),
        (
            pyodbc.ProgrammingError("42000", "permission denied (229) " + SECRET),
            "database-privileges",
        ),
        (pyodbc.OperationalError("08001", SECRET), "database-connection"),
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
        (
            pyodbc.ProgrammingError("42000", "permission denied (229) " + SECRET),
            "database-privileges",
        ),
        (pyodbc.OperationalError("HYT00", "lock timeout (1222) " + SECRET), "migration-timeout"),
        (pyodbc.OperationalError("HYT00", SECRET), "migration-timeout"),
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
