"""Random browser tokens and hash-only persistence; no browser fingerprinting."""

import hashlib
import re
import secrets

from app.database import utc_now
from app.extensions import db
from app.models import StudentIdentity


def new_token():
    return secrets.token_urlsafe(32)


def valid_token(token):
    return isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is not None


def token_hash(token):
    if not valid_token(token):
        raise ValueError("A valid browser token is required.")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def find_identity(token):
    return db.session.scalar(
        db.select(StudentIdentity).where(StudentIdentity.public_token_hash == token_hash(token))
    )


def identity_for_join(token):
    """Upsert inside the queue transaction, including simultaneous first joins."""
    hashed = token_hash(token)
    identity = db.session.scalar(
        db.select(StudentIdentity)
        .where(StudentIdentity.public_token_hash == hashed)
        .with_hint(StudentIdentity, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    if identity is None:
        identity = StudentIdentity(public_token_hash=hashed)
        db.session.add(identity)
    else:
        identity.last_seen_at = utc_now()
    db.session.flush()
    return identity
