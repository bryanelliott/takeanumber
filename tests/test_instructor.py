from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.services import EmailAlreadyRegistered, register_instructor
from app.extensions import db
from app.models import Instructor
from app.models.instructor import normalize_email


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        (" \tTeacher@EXAMPLE.EDU\n", "teacher@example.edu"),
        ("First.Last+LAB@Example.edu", "first.last+lab@example.edu"),
        ("Teacher@BÜCHER.DE", "teacher@xn--bcher-kva.de"),
    ],
)
def test_email_normalization(email, expected):
    assert normalize_email(email) == expected


@pytest.mark.parametrize("email", ["élise@example.edu", "not an address", "a@localhost"])
def test_invalid_or_unicode_local_part_is_rejected(email):
    with pytest.raises(ValueError):
        normalize_email(email)


def test_password_hashes_are_salted_and_preserve_spaces():
    first, second = Instructor(), Instructor()
    password = " a long password with spaces "
    first.set_password(password)
    second.set_password(password)
    assert first.password_hash.startswith("scrypt:32768:8:3$")
    assert first.password_hash != second.password_hash
    assert first.check_password(password)
    assert not first.check_password(password.strip())
    assert not first.check_password("wrong password")
    assert password not in first.password_hash


def test_registration_rolls_back_duplicate_and_can_continue(app, auth_db, signup_data):
    with app.app_context():
        first = register_instructor("teacher@example.edu", "Teacher", signup_data["password"])
        assert isinstance(first.id, UUID)
        with pytest.raises(EmailAlreadyRegistered):
            register_instructor("TEACHER@example.edu", "Duplicate", signup_data["password"])
        second = register_instructor("second@example.edu", "Second", signup_data["password"])
        assert second.id != first.id


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "TEACHER@example.edu"},
        {"email": " teacher@example.edu "},
        {"display_name": " \t "},
        {"display_name": None},
        {"password_hash": "plaintext password"},
        {"password_hash": None},
        {"email": None},
    ],
)
def test_database_constraints_reject_invalid_direct_inserts(app, auth_db, changes):
    values = {
        "id": uuid4(),
        "email": "teacher@example.edu",
        "display_name": "Teacher",
        "password_hash": "scrypt:test-constraint-placeholder",
    }
    values.update(changes)
    with app.app_context():
        with pytest.raises(IntegrityError):
            db.session.execute(Instructor.__table__.insert().values(**values))
            db.session.commit()
        db.session.rollback()


def test_database_unique_constraint(app, auth_db, signup_data):
    with app.app_context():
        first = register_instructor("teacher@example.edu", "Teacher", signup_data["password"])
        with pytest.raises(IntegrityError):
            db.session.execute(
                Instructor.__table__.insert().values(
                    id=uuid4(),
                    email=first.email,
                    display_name="Duplicate",
                    password_hash=first.password_hash,
                )
            )
            db.session.commit()
        db.session.rollback()
