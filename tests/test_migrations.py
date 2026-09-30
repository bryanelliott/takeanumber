from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, Instructor
from app.services import sessions

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")


def test_initial_migration_downgrade_upgrade_and_model_match(migrated_schema):
    with migrated_schema.app_context():
        db.session.remove()
        try:
            downgrade(directory=MIGRATIONS, revision="base")
            assert "instructor" not in inspect(db.engine).get_table_names()
            assert "help_session" not in inspect(db.engine).get_table_names()
            assert "student_identity" not in inspect(db.engine).get_table_names()
            assert "queue_entry" not in inspect(db.engine).get_table_names()
        finally:
            upgrade(directory=MIGRATIONS)
        with db.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0003_student_queue"
            )
            context = MigrationContext.configure(connection, opts={"compare_server_default": True})
            assert compare_metadata(context, db.metadata) == []


def test_help_session_migration_preserves_instructors(migrated_schema):
    with migrated_schema.app_context():
        instructor = register_instructor(
            "migration@example.edu", "Migration test", "a sufficiently long password"
        )
        identity = instructor.id
        db.session.remove()
        try:
            downgrade(directory=MIGRATIONS, revision="0001_instructor")
            assert "help_session" not in inspect(db.engine).get_table_names()
            assert db.session.get(Instructor, identity).display_name == "Migration test"
            db.session.remove()
            upgrade(directory=MIGRATIONS)
            assert "help_session" in inspect(db.engine).get_table_names()
            assert db.session.get(Instructor, identity).email == "migration@example.edu"
        finally:
            db.session.remove()
            upgrade(directory=MIGRATIONS)
            db.session.execute(db.delete(Instructor).where(Instructor.id == identity))
            db.session.commit()


def test_student_queue_migration_preserves_sessions(migrated_schema):
    with migrated_schema.app_context():
        owner = register_instructor(
            "queue-migration@example.edu", "Migration", "a long test password"
        )
        owner_id = owner.id
        help_session = sessions.start_session(owner_id)
        session_id, code = help_session.id, help_session.public_code
        db.session.remove()
        try:
            downgrade(directory=MIGRATIONS, revision="0002_help_session")
            assert "queue_entry" not in inspect(db.engine).get_table_names()
            assert "student_identity" not in inspect(db.engine).get_table_names()
            assert db.session.get(HelpSession, session_id).public_code == code
            db.session.remove()
            upgrade(directory=MIGRATIONS)
            assert {"queue_entry", "student_identity"} <= set(inspect(db.engine).get_table_names())
            assert db.session.get(HelpSession, session_id).next_queue_number == 1
        finally:
            db.session.remove()
            upgrade(directory=MIGRATIONS)
            db.session.execute(db.delete(HelpSession).where(HelpSession.id == session_id))
            db.session.execute(db.delete(Instructor).where(Instructor.id == owner_id))
            db.session.commit()
