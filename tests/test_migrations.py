import shutil
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app.extensions import db
from app.models import InstructorSetting, QueueEntry
from app.services import queue, student_identity

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def test_initial_migration_downgrade_upgrade_and_model_match(migrated_schema):
    with migrated_schema.app_context():
        db.session.remove()
        try:
            downgrade(directory=MIGRATIONS, revision="base")
            assert not set(db.metadata.tables) & set(inspect(db.engine).get_table_names())
        finally:
            upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0001_sqlserver_baseline"
            )
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert compare_metadata(context, db.metadata) == []


def test_repeated_baseline_upgrade_preserves_accounts_preferences_and_queue(app, queue_session):
    with app.app_context():
        entry = queue.join(queue_session[1], student_identity.new_token(), "Preserved name")
        entry_id = entry.id
        queue.begin_serving(*queue_session, entry_id)
        joined, started = entry.joined_at, entry.service_started_at
        preferences = db.session.scalar(
            db.select(InstructorSetting).where(InstructorSetting.instructor_id == queue_session[0])
        )
        preferences.sound_alert_enabled = False
        preference_id = preferences.id
        db.session.commit()
        db.session.remove()
        upgrade(directory=MIGRATIONS)
        upgrade(directory=MIGRATIONS)
        saved = db.session.get(QueueEntry, entry_id)
        assert saved.status == "serving" and saved.display_name == "Preserved name"
        assert (saved.joined_at, saved.service_started_at) == (joined, started)
        assert db.session.get(InstructorSetting, preference_id).sound_alert_enabled is False
        indexes = {i["name"] for i in inspect(db.engine).get_indexes("queue_entry")}
        assert {"uq_queue_entry_serving_session", "uq_queue_entry_active_identity"} <= indexes


def test_future_revision_upgrades_from_baseline_and_preserves_data(app, queue_session, tmp_path):
    directory = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, directory)
    (directory / "versions" / "0002_test_extension.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        "revision = '0002_test_extension'\ndown_revision = '0001_sqlserver_baseline'\n"
        "def upgrade():\n"
        "    op.add_column('instructor', "
        "sa.Column('test_extension', sa.Integer(), nullable=True))\n"
        "def downgrade():\n"
        "    op.drop_column('instructor', 'test_extension')\n"
    )
    with app.app_context():
        migration = app.extensions["migrate"].migrate
        config = migration.get_config()
        config.set_main_option("script_location", str(directory))
        try:
            with patch.object(migration, "get_config", return_value=config):
                result = app.test_cli_runner().invoke(args=["deploy-upgrade"])
            assert result.exit_code == 0, result.output
            with db.engine.connect() as connection:
                assert MigrationContext.configure(connection).get_current_heads() == (
                    "0002_test_extension",
                )
                assert connection.scalar(text("SELECT COUNT(*) FROM instructor")) == 1
            assert "test_extension" in {
                column["name"] for column in inspect(db.engine).get_columns("instructor")
            }
        finally:
            config.attributes.pop("connection", None)
            command.downgrade(config, "0001_sqlserver_baseline")
