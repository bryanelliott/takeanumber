"""Instructor accounts; no student identities are stored here."""

from datetime import UTC, datetime
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

PASSWORD_METHOD = "scrypt:32768:8:3"


def normalize_email(value):
    """Case-insensitive accounts, ASCII local parts, and IDNA-normalized domains."""
    try:
        address = validate_email(
            value.strip(), check_deliverability=False, allow_smtputf8=False
        ).ascii_email.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid email address.") from None
    if len(address) > 254:
        raise ValueError("Email must be at most 254 characters.")
    return address


class Instructor(UserMixin, db.Model):
    __tablename__ = "instructor"
    __table_args__ = (
        db.UniqueConstraint("email", name="uq_instructor_email"),
        db.CheckConstraint(
            "email = lower(email) AND email = btrim(email) AND length(email) > 0",
            name="ck_instructor_email_normalized",
        ),
        db.CheckConstraint(
            "display_name ~ '[^[:space:]]'", name="ck_instructor_display_name_required"
        ),
        db.CheckConstraint("password_hash LIKE 'scrypt:%'", name="ck_instructor_password_hash"),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    email = db.Column(db.String(254), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    @validates("email")
    def validate_email(self, key, value):
        return normalize_email(value)

    @validates("display_name")
    def validate_display_name(self, key, value):
        value = value.strip()
        if not 1 <= len(value) <= 100:
            raise ValueError("Display name must be 1–100 characters.")
        return value

    def set_password(self, password):
        if not 15 <= len(password) <= 128:
            raise ValueError("Password must be 15–128 characters.")
        self.password_hash = generate_password_hash(password, method=PASSWORD_METHOD)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
