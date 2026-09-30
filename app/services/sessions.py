"""Atomic session lifecycle and ownership-scoped queries."""

import secrets
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import HelpSession, Instructor


class SessionNotFound(LookupError):
    """Missing and other instructors' sessions are intentionally indistinguishable."""


class SessionEnded(ValueError):
    """The session is no longer open for student requests."""


def active_session(instructor_id):
    return db.session.scalar(
        db.select(HelpSession)
        .where(HelpSession.instructor_id == instructor_id, HelpSession.status == "active")
        .execution_options(populate_existing=True)
    )


def owned_session(instructor_id, public_code, *, lock=False):
    query = (
        db.select(HelpSession)
        .where(HelpSession.instructor_id == instructor_id, HelpSession.public_code == public_code)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    help_session = db.session.scalar(query)
    if help_session is None:
        raise SessionNotFound()
    return help_session


def start_session(instructor_id):
    """Commit one new session or return the existing active session on retry."""
    try:
        # Serialize concurrent starts even before a session row exists. The partial
        # unique index independently enforces the invariant for all database writers.
        instructor = db.session.scalar(
            db.select(Instructor)
            .where(Instructor.id == instructor_id, Instructor.is_active.is_(True))
            .with_for_update()
        )
        if instructor is None:
            raise SessionNotFound()
        help_session = active_session(instructor_id)
        if help_session is None:
            for _ in range(3):
                try:
                    # A code collision rolls back only this insertion, retaining the
                    # instructor lock while generating a fresh 128-bit public code.
                    with db.session.begin_nested():
                        help_session = HelpSession(
                            instructor_id=instructor_id, public_code=secrets.token_urlsafe(16)
                        )
                        db.session.add(help_session)
                        db.session.flush()
                    break
                except IntegrityError as error:
                    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                    if constraint != "uq_help_session_public_code":
                        raise
            else:
                raise RuntimeError("Unable to allocate a unique session code.")
        db.session.commit()
        return help_session
    except Exception:
        db.session.rollback()
        raise


def end_session(instructor_id, public_code):
    """Commit the active-to-ended transition once, preserving its original time."""
    try:
        help_session = owned_session(instructor_id, public_code, lock=True)
        if help_session.status == "active":
            help_session.status = "ended"
            help_session.ended_at = datetime.now(UTC)
        db.session.commit()
        return help_session
    except Exception:
        db.session.rollback()
        raise


def session_for_join(public_code):
    """Lock and validate a session inside the caller's future join transaction.

    Never commits: a future QueueService must insert the entry before committing
    this same transaction, or roll back on failure. No student joins exist yet.
    """
    help_session = db.session.scalar(
        db.select(HelpSession)
        .where(HelpSession.public_code == public_code)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if help_session is None:
        raise SessionNotFound()
    if not help_session.accepts_joins:
        raise SessionEnded()
    return help_session
