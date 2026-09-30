from sqlalchemy import text

from app.extensions import db


def test_connection_uses_dedicated_postgresql_database(app):
    with app.app_context(), db.engine.connect() as connection:
        database, username = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()
        assert db.engine.dialect.name == "postgresql"
        assert database == db.engine.url.database
        assert username == db.engine.url.username
        assert database.endswith("_test")
        assert username.endswith("_test")


def test_database_check_command(app):
    result = app.test_cli_runner().invoke(args=["check-db"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "PostgreSQL connection OK."
