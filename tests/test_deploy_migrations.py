from unittest.mock import patch

from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app.extensions import db


def test_deployment_requires_a_single_release_head(app):
    for heads in [[], ["first", "second"]]:
        with patch("app.cli.ScriptDirectory.from_config") as scripts:
            scripts.return_value.get_heads.return_value = heads
            with patch("app.cli.command.upgrade") as migrate:
                result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
        assert result.exit_code != 0
        assert "exactly one migration head" in result.output
        migrate.assert_not_called()


def test_deployment_sets_transaction_local_timeouts(app, auth_db):
    from app.cli import command

    real_upgrade = command.upgrade

    def inspect_timeouts(config, revision):
        connection = config.attributes["connection"]
        assert connection.in_transaction()
        assert connection.scalar(text("SELECT @@LOCK_TIMEOUT")) == 5000
        assert connection.connection.driver_connection.timeout == 120
        real_upgrade(config, revision)

    with patch("app.cli.command.upgrade", side_effect=inspect_timeouts):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code == 0, result.output


def test_deployment_head_mismatch_rolls_back(app, auth_db):
    def wrong_head(config, revision):
        config.attributes["connection"].execute(
            text("UPDATE alembic_version SET version_num = 'wrong-head'")
        )

    with patch("app.cli.command.upgrade", side_effect=wrong_head):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code != 0
    assert "Database revision does not match the release" in result.output
    with app.app_context(), db.engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_heads() == (
            "0001_sqlserver_baseline",
        )


def test_deployment_upgrade_is_repeatable(app, auth_db):
    for _ in range(2):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
        assert result.exit_code == 0, result.output
        assert "Database upgraded to the release head" in result.output


def test_deployment_lock_blocks_competing_migration(app, auth_db):
    with app.app_context(), db.engine.begin() as connection:
        connection.execute(text("IF @@TRANCOUNT = 0 BEGIN TRANSACTION"))
        connection.execute(
            text(
                "EXEC sys.sp_getapplock @Resource='TakeANumber:deploy-upgrade', "
                "@LockMode='Exclusive', @LockOwner='Transaction', @DbPrincipal='public'"
            )
        )
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
        assert result.exit_code != 0
        assert "Another deployment migration is running" in result.output
    assert app.test_cli_runner().invoke(args=["deploy-upgrade"]).exit_code == 0


def test_failed_migration_rolls_back_and_hides_sensitive_errors(app, auth_db):
    def failing_upgrade(config, revision):
        connection = config.attributes["connection"]
        connection.execute(text("UPDATE alembic_version SET version_num = 'failed-migration'"))
        raise RuntimeError("secret-connection-password and private student data")

    with patch("app.cli.command.upgrade", side_effect=failing_upgrade):
        result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
    assert result.exit_code != 0 and "deployment blocked" in result.output
    assert "secret-connection-password" not in result.output
    with app.app_context(), db.engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_heads() == (
            "0001_sqlserver_baseline",
        )
    assert app.test_cli_runner().invoke(args=["deploy-upgrade"]).exit_code == 0


def test_deployment_outer_transaction_rolls_back_actual_schema_changes(app, auth_db):
    from app.cli import command

    real_upgrade = command.upgrade

    def fail_after_upgrade(config, revision):
        real_upgrade(config, revision)
        raise RuntimeError("failure after DDL")

    with app.app_context():
        db.session.remove()
        try:
            downgrade(revision="base")
            with patch("app.cli.command.upgrade", side_effect=fail_after_upgrade):
                result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
            assert result.exit_code != 0
            assert "instructor_setting" not in inspect(db.engine).get_table_names()
            with db.engine.connect() as connection:
                assert MigrationContext.configure(connection).get_current_heads() == ()
            result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
            assert result.exit_code == 0, result.output
            assert "instructor_setting" in inspect(db.engine).get_table_names()
        finally:
            upgrade()
