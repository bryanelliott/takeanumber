"""Instructor registration, credential checks, and session identity loading."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import Instructor
from app.models.instructor import PASSWORD_METHOD, normalize_email

# Unknown emails still incur a password check. This value never represents an account.
DUMMY_PASSWORD_HASH = generate_password_hash("unused-account-password", method=PASSWORD_METHOD)


class EmailAlreadyRegistered(ValueError):
    pass


def register_instructor(email, display_name, password):
    instructor = Instructor(email=email, display_name=display_name)
    instructor.set_password(password)
    db.session.add(instructor)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == (
            "uq_instructor_email"
        ):
            raise EmailAlreadyRegistered("Unable to create an account with that email.") from None
        raise
    return instructor


def authenticate(email, password):
    instructor = db.session.scalar(
        db.select(Instructor).where(Instructor.email == normalize_email(email))
    )
    password_hash = instructor.password_hash if instructor else DUMMY_PASSWORD_HASH
    valid = check_password_hash(password_hash, password)
    return instructor if instructor and valid and instructor.is_active else None


def load_instructor(user_id):
    try:
        identity = UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        return None
    instructor = db.session.get(Instructor, identity)
    return instructor if instructor and instructor.is_active else None
