"""Atomic queue transitions and ownership-scoped Master/Client View snapshots."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.extensions import db
from app.models import HelpSession, Instructor, QueueEntry
from app.models.queue_entry import ACTIVE_STATUSES
from app.realtime import publish_queue_changed
from app.services import sessions, student_identity
from app.services.wait_time import WaitTimeService


class EntryNotFound(LookupError):
    pass


MASTER_QUEUE_LIMIT = 5


@dataclass(frozen=True)
class MasterEntry:
    id: UUID
    queue_number: int
    display_name: str | None


@dataclass(frozen=True)
class MasterState:
    public_code: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    serving: MasterEntry | None
    waiting: tuple[MasterEntry, ...]
    waiting_count: int

    @property
    def next_up(self):
        return self.waiting[0] if self.waiting else None


def _entry_snapshot(entry):
    return MasterEntry(entry.id, entry.queue_number, entry.display_name) if entry else None


def master_state(instructor_id, public_code):
    """Read one ownership-scoped snapshot while excluding concurrent mutations."""
    try:
        help_session = db.session.scalar(
            db.select(HelpSession)
            .where(
                HelpSession.instructor_id == instructor_id,
                HelpSession.public_code == public_code,
            )
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if help_session is None:
            raise sessions.SessionNotFound()
        serving, waiting, count = None, (), 0
        if help_session.status == "active":
            serving = _entry_snapshot(_serving_entry(help_session.id))
            waiting_query = db.select(QueueEntry).where(
                QueueEntry.session_id == help_session.id, QueueEntry.status == "waiting"
            )
            waiting = tuple(
                _entry_snapshot(entry)
                for entry in db.session.scalars(
                    waiting_query.order_by(QueueEntry.queue_number)
                    .limit(MASTER_QUEUE_LIMIT)
                    .execution_options(populate_existing=True)
                )
            )
            count = db.session.scalar(
                db.select(db.func.count()).select_from(waiting_query.subquery())
            )
        state = MasterState(
            help_session.public_code,
            help_session.status,
            help_session.started_at,
            help_session.ended_at,
            serving,
            waiting,
            count,
        )
        db.session.commit()
        return state
    except Exception:
        db.session.rollback()
        raise


def _serving_entry(session_id):
    return db.session.execute(
        db.select(QueueEntry)
        .where(QueueEntry.session_id == session_id, QueueEntry.status == "serving")
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()


def begin_serving(instructor_id, public_code, entry_id):
    """Start the displayed Next Up only when nobody is serving."""
    return _advance(instructor_id, public_code, entry_id, complete=False)


def complete_current(instructor_id, public_code, entry_id):
    """Complete the displayed current request and start the next, atomically."""
    return _advance(instructor_id, public_code, entry_id, complete=True)


def _advance(instructor_id, public_code, entry_id, *, complete):
    try:
        help_session = sessions.owned_session(instructor_id, public_code, lock=True)
        if help_session.status != "active":
            raise sessions.SessionEnded()
        try:
            target_id = UUID(str(entry_id))
        except (ValueError, TypeError):
            raise EntryNotFound() from None
        serving = _serving_entry(help_session.id)
        next_entry = db.session.scalar(
            db.select(QueueEntry)
            .where(QueueEntry.session_id == help_session.id, QueueEntry.status == "waiting")
            .order_by(QueueEntry.queue_number)
            .limit(1)
            .execution_options(populate_existing=True)
        )
        if complete:
            applicable = serving is not None and serving.id == target_id
        else:
            applicable = serving is None and next_entry is not None and next_entry.id == target_id
        if not applicable:
            # A stale form or double click must never complete a different request.
            db.session.commit()
            return False
        # Read wall time after acquiring the lock, not transaction-start time.
        transitioned_at = db.session.scalar(db.select(db.func.clock_timestamp()))
        if complete:
            serving.status = "completed"
            serving.completed_at = transitioned_at
            # Release the partial unique index slot before promoting the next row.
            db.session.flush()
        if next_entry is not None:
            next_entry.status = "serving"
            next_entry.service_started_at = transitioned_at
        db.session.commit()
        publish_queue_changed(public_code)
        return True
    except Exception:
        db.session.rollback()
        raise


@dataclass(frozen=True)
class ClientState:
    public_code: str
    instructor_name: str
    status: str
    entry_id: str | None = None
    queue_number: int | None = None
    display_name: str | None = None
    people_ahead: int | None = None
    estimated_wait_minutes: int | None = None


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
        changed = entry is None
        if changed:
            entry = QueueEntry(
                session_id=help_session.id,
                student_identity_id=identity.id,
                queue_number=help_session.next_queue_number,
                display_name=name,
            )
            help_session.next_queue_number += 1
            db.session.add(entry)
        db.session.commit()
        if changed:
            publish_queue_changed(public_code)
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
        changed = entry.status in ACTIVE_STATUSES
        if changed:
            entry.status = "left"
            entry.left_at = db.func.clock_timestamp()
            identity.last_seen_at = db.func.clock_timestamp()
        db.session.commit()
        if changed:
            publish_queue_changed(public_code)
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
            WaitTimeService.estimate_minutes(help_session, ahead) if status == "waiting" else None,
        )
        db.session.commit()
        return state
    except Exception:
        db.session.rollback()
        raise
