"""Server-authoritative joining, leaving, and private Client View state."""

from dataclasses import dataclass
from uuid import UUID

from app.extensions import db
from app.models import HelpSession, Instructor, QueueEntry
from app.models.queue_entry import ACTIVE_STATUSES
from app.services import sessions, student_identity


class EntryNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ClientState:
    public_code: str
    instructor_name: str
    status: str
    entry_id: str | None = None
    queue_number: int | None = None
    display_name: str | None = None
    people_ahead: int | None = None


def join(public_code, token, display_name=None):
    name = (display_name or "").strip() or None
    if name is not None and len(name) > 100:
        raise ValueError("Name must be at most 100 characters.")
    try:
        help_session = sessions.session_for_join(public_code)
        identity = student_identity.identity_for_join(token)
        entry = db.session.scalar(
            db.select(QueueEntry)
            .where(
                QueueEntry.session_id == help_session.id,
                QueueEntry.student_identity_id == identity.id,
                QueueEntry.status.in_(ACTIVE_STATUSES),
            )
            .execution_options(populate_existing=True)
        )
        if entry is None:
            entry = QueueEntry(
                session_id=help_session.id,
                student_identity_id=identity.id,
                queue_number=help_session.next_queue_number,
                display_name=name,
            )
            help_session.next_queue_number += 1
            db.session.add(entry)
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        raise


def leave(public_code, token, entry_id):
    """Target the rendered request, so retrying an old Leave cannot remove a rejoin."""
    try:
        help_session = sessions.session_for_join(public_code)
        identity = student_identity.find_identity(token)
        try:
            target_id = UUID(str(entry_id))
        except (ValueError, TypeError):
            raise EntryNotFound() from None
        if identity is None:
            raise EntryNotFound()
        entry = db.session.scalar(
            db.select(QueueEntry)
            .where(
                QueueEntry.id == target_id,
                QueueEntry.session_id == help_session.id,
                QueueEntry.student_identity_id == identity.id,
            )
            .execution_options(populate_existing=True)
        )
        if entry is None:
            raise EntryNotFound()
        if entry.status in ACTIVE_STATUSES:
            entry.status = "left"
            entry.left_at = db.func.clock_timestamp()
            identity.last_seen_at = db.func.clock_timestamp()
        db.session.commit()
        return entry
    except Exception:
        db.session.rollback()
        raise


def client_state(public_code, token=None):
    """Return a consistent snapshot without exposing another browser's request."""
    try:
        row = db.session.execute(
            db.select(HelpSession, Instructor.display_name)
            .join(Instructor, HelpSession.instructor_id == Instructor.id)
            .where(HelpSession.public_code == public_code)
            .with_for_update(read=True, of=HelpSession)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if row is None:
            raise sessions.SessionNotFound()
        help_session, instructor_name = row
        identity = student_identity.find_identity(token) if token else None
        entry = None
        if identity:
            entry = db.session.scalar(
                db.select(QueueEntry)
                .where(
                    QueueEntry.session_id == help_session.id,
                    QueueEntry.student_identity_id == identity.id,
                )
                .order_by(QueueEntry.queue_number.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        status = (
            "ended" if help_session.status == "ended" else (entry.status if entry else "not_joined")
        )
        ahead = None
        if status in ACTIVE_STATUSES:
            ahead = db.session.scalar(
                db.select(db.func.count())
                .select_from(QueueEntry)
                .where(
                    QueueEntry.session_id == help_session.id,
                    QueueEntry.status.in_(ACTIVE_STATUSES),
                    QueueEntry.queue_number < entry.queue_number,
                )
            )
        state = ClientState(
            public_code,
            instructor_name,
            status,
            str(entry.id) if entry else None,
            entry.queue_number if entry else None,
            entry.display_name if entry else None,
            ahead,
        )
        db.session.commit()
        return state
    except Exception:
        db.session.rollback()
        raise
