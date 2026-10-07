"""Connection retries must never turn a failed write into a duplicate mutation."""

from unittest.mock import patch

import pyodbc
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.database import connect_attempts
from app.extensions import db


def test_idle_connections_are_closed_and_driver_pooling_disabled(app):
    assert pyodbc.pooling is False
    with app.app_context():
        assert isinstance(db.engine.pool, NullPool)
        assert db.engine.hide_parameters
        assert db.engine.url.query["ConnectRetryCount"] == "0"
        with db.engine.connect() as connection:
            raw = connection.connection.driver_connection
            assert raw.timeout == 30
            assert connection.scalar(text("SELECT @@LOCK_TIMEOUT")) == 5000
        with pytest.raises(pyodbc.ProgrammingError):
            raw.cursor()


def test_cold_database_retries_only_connection_open(app):
    real_connect = pyodbc.connect
    attempts = []

    def waking(*args, **kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise pyodbc.OperationalError("42000", "Database unavailable (40613)")
        return real_connect(*args, **kwargs)

    with app.app_context(), patch("pyodbc.connect", side_effect=waking):
        with patch("app.database.time.sleep") as sleep:
            with db.engine.connect() as connection:
                assert connection.scalar(text("SELECT 1")) == 1
    assert len(attempts) == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


@pytest.mark.parametrize("state, code, expected", [("28000", 18456, 1), ("42000", 40613, 3)])
def test_connection_failures_have_bounded_retries(app, state, code, expected):
    with app.app_context(), patch("pyodbc.connect") as connect:
        connect.side_effect = pyodbc.OperationalError(state, f"sensitive password ({code})")
        with patch("app.database.time.sleep"):
            with pytest.raises(DBAPIError):
                db.engine.connect()
        assert connect.call_count == expected


def test_migration_has_longer_resume_budget_and_restores_request_budget(app, auth_db):
    budgets = []
    real_connect = pyodbc.connect

    def opening(*args, **kwargs):
        budgets.append(connect_attempts.get())
        return real_connect(*args, **kwargs)

    with patch("pyodbc.connect", side_effect=opening):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code == 0, result.output
    assert budgets == [20]
    assert connect_attempts.get() == 3


def test_statement_failure_is_not_retried(app):
    # Only successful connection opening can be retried; statement failure propagates.
    with app.app_context(), db.engine.connect() as connection:
        with patch.object(db.engine.dialect, "do_execute") as execute:
            execute.side_effect = pyodbc.OperationalError("08S01", "Connection lost (40197)")
            with pytest.raises(DBAPIError):
                connection.execute(text("SELECT 1"))
            assert execute.call_count == 1


def test_health_never_opens_database_even_with_a_session_cookie(client):
    with client.session_transaction() as session:
        session["_user_id"] = "11111111-1111-1111-1111-111111111111"
        session["_fresh"] = True
    with patch("pyodbc.connect", side_effect=AssertionError("health woke database")) as connect:
        assert client.get("/health").json == {"status": "ok"}
        connect.assert_not_called()


def test_exhausted_request_returns_safe_503_without_replaying(app, caplog):
    @app.get("/test-database-failure")
    def database_failure():
        db.session.execute(text("SELECT 1"))

    with patch("pyodbc.connect") as connect, patch("app.database.time.sleep"):
        connect.side_effect = pyodbc.OperationalError("42000", "secret password (40613)")
        result = app.test_client().get("/test-database-failure")
        assert connect.call_count == 3
    assert result.status_code == 503
    assert result.headers["Retry-After"] == "5"
    assert "secret password" not in result.text + caplog.text
