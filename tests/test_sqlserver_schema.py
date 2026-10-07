"""SQL Server storage semantics must preserve the application's schema invariants."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.services import register_instructor
from app.extensions import db
from app.models import HelpSession, Instructor, QueueEntry, StudentIdentity
from app.services import queue, student_identity


def test_unicode_names_roundtrip_at_character_limit(app, queue_session):
    name = "\U0001f600" * 100
    with app.app_context():
        instructor = register_instructor("unicode@example.edu", name, "a long test password")
        identity = instructor.id
        entry = queue.join(queue_session[1], student_identity.new_token(), name)
        entry_id = entry.id
        db.session.remove()
        assert db.session.get(Instructor, identity).display_name == name
        assert db.session.get(QueueEntry, entry_id).display_name == name


@pytest.mark.parametrize("name", ["x" * 101, "\U0001f600" * 99 + "ab"])
def test_database_enforces_name_character_limit(app, auth_db, name):
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(
                Instructor.__table__.insert().values(
                    id=uuid4(),
                    email="long@example.edu",
                    display_name=name,
                    password_hash="scrypt:test",
                    is_active=True,
                )
            )
            db.session.commit()
        db.session.rollback()


def test_codes_are_case_sensitive_and_null_token_hashes_are_not_unique(app, queue_session):
    with app.app_context():
        instructor = register_instructor("case@example.edu", "Case", "a long test password")
        first = db.session.scalar(db.select(HelpSession))
        first.public_code = "a" * 22
        db.session.add(HelpSession(instructor_id=instructor.id, public_code="A" * 22))
        db.session.add_all([StudentIdentity(public_token_hash=None) for _ in range(2)])
        db.session.commit()
        assert (
            db.session.scalar(db.select(HelpSession).where(HelpSession.public_code == "a" * 22)).id
            == first.id
        )
        assert db.session.scalar(db.select(db.func.count()).select_from(StudentIdentity)) == 2


@pytest.mark.parametrize("status", ["ACTIVE", "active "])
def test_noncanonical_status_is_rejected_by_database(app, queue_session, status):
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(db.update(HelpSession).values(status=status))
            db.session.commit()
        db.session.rollback()


def test_test_user_has_schema_rights_but_is_not_database_owner(app):
    with app.app_context(), db.engine.connect() as connection:
        assert connection.scalar(db.text("SELECT IS_ROLEMEMBER('db_owner')")) == 0
        assert (
            connection.scalar(db.text("SELECT HAS_PERMS_BY_NAME('dbo', 'SCHEMA', 'CONTROL')")) == 1
        )
        assert (
            connection.scalar(
                db.text("SELECT HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE')")
            )
            == 1
        )


@pytest.mark.parametrize("name", [" \t\v\f\r\n", "\u2003\u3000\u00a0"])
def test_database_rejects_whitespace_only_name(app, auth_db, name):
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(
                Instructor.__table__.insert().values(
                    id=uuid4(),
                    email="blank@example.edu",
                    display_name=name,
                    password_hash="scrypt:test",
                    is_active=True,
                )
            )
            db.session.commit()
        db.session.rollback()
