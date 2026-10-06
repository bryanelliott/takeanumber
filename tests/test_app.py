from unittest.mock import patch

from sqlalchemy.exc import OperationalError


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_database_check_reports_failure_without_credentials(app):
    with patch("app.cli.db") as database:
        database.engine.connect.side_effect = OperationalError(
            "sensitive connection details", None, Exception("secret password")
        )
        result = app.test_cli_runner().invoke(args=["check-db"])
    assert result.exit_code == 1
    assert "[database-connection]" in result.output
    assert "secret password" not in result.output
    assert "sensitive connection details" not in result.output
