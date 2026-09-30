from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app.extensions import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def test_initial_migration_downgrade_upgrade_and_model_match(migrated_schema):
    with migrated_schema.app_context():
        db.session.remove()
        try:
            downgrade(directory=MIGRATIONS, revision="base")
            assert "instructor" not in inspect(db.engine).get_table_names()
        finally:
            upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0001_instructor"
            )
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert compare_metadata(context, db.metadata) == []
