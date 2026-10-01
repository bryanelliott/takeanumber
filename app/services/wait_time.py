"""Read-only WaitTimeService; policy is documented in docs/architecture.md."""

from datetime import timedelta
from math import ceil

from app.extensions import db
from app.models import HelpSession, QueueEntry


class WaitTimeService:
    MIN_CURRENT_COMPLETIONS = 3
    HISTORY_LOOKBACK = timedelta(days=90)

    @classmethod
    def estimate_minutes(cls, help_session, people_ahead, *, as_of=None):
        """Return rounded minutes or None; the caller owns the snapshot transaction.

        Never commits or changes rows. Client state calls this while holding the
        session's shared lock, so queue position and current history agree.
        """
        if people_ahead < 0:
            raise ValueError("People ahead cannot be negative.")
        if help_session.status != "active":
            return None
        if people_ahead == 0:
            return 0
        if as_of is None:
            as_of = db.session.scalar(db.select(db.func.clock_timestamp()))
        if as_of.utcoffset() is None:
            raise ValueError("Calculation time must be timezone-aware.")

        duration = db.extract("epoch", QueueEntry.completed_at - QueueEntry.service_started_at)
        valid = (
            QueueEntry.status == "completed",
            QueueEntry.joined_at.is_not(None),
            QueueEntry.service_started_at.is_not(None),
            QueueEntry.completed_at.is_not(None),
            QueueEntry.left_at.is_(None),
            QueueEntry.service_started_at >= QueueEntry.joined_at,
            QueueEntry.completed_at > QueueEntry.service_started_at,
            QueueEntry.completed_at <= as_of,
        )
        count, average = db.session.execute(
            db.select(db.func.count(QueueEntry.id), db.func.avg(duration)).where(
                QueueEntry.session_id == help_session.id,
                *valid,
            )
        ).one()
        if count < cls.MIN_CURRENT_COMPLETIONS:
            average = db.session.scalar(
                db.select(db.func.avg(duration))
                .join(HelpSession, HelpSession.id == QueueEntry.session_id)
                .where(
                    *valid,
                    HelpSession.instructor_id == help_session.instructor_id,
                    HelpSession.id != help_session.id,
                    HelpSession.status == "ended",
                    HelpSession.ended_at <= as_of,
                    QueueEntry.completed_at <= HelpSession.ended_at,
                    QueueEntry.completed_at >= as_of - cls.HISTORY_LOOKBACK,
                )
            )
        if average is None:
            return None
        # PostgreSQL numeric averages preserve fractional seconds; round only once.
        return ceil(average * people_ahead / 60)
