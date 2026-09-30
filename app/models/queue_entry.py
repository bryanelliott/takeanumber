"""A historical help request belonging to a browser profile and session."""

from uuid import uuid4

from app.extensions import db

ACTIVE_STATUSES = ("waiting", "serving")


class QueueEntry(db.Model):
    __tablename__ = "queue_entry"
    __table_args__ = (
        db.UniqueConstraint("session_id", "queue_number", name="uq_queue_entry_session_number"),
        db.Index(
            "uq_queue_entry_active_identity",
            "session_id",
            "student_identity_id",
            unique=True,
            postgresql_where=db.text("status IN ('waiting', 'serving')"),
        ),
        db.CheckConstraint("queue_number >= 1", name="ck_queue_entry_number"),
        db.CheckConstraint(
            "status IN ('waiting', 'serving', 'completed', 'left')", name="ck_queue_entry_status"
        ),
        db.CheckConstraint(
            "(status = 'waiting' AND service_started_at IS NULL AND completed_at IS NULL "
            "AND left_at IS NULL) OR "
            "(status = 'serving' AND service_started_at IS NOT NULL AND completed_at IS NULL "
            "AND left_at IS NULL) OR "
            "(status = 'completed' AND service_started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND left_at IS NULL) OR "
            "(status = 'left' AND completed_at IS NULL AND left_at IS NOT NULL)",
            name="ck_queue_entry_state_times",
        ),
        db.CheckConstraint(
            "service_started_at >= joined_at AND completed_at >= service_started_at "
            "AND left_at >= joined_at AND left_at >= service_started_at",
            name="ck_queue_entry_time_order",
        ),
        db.CheckConstraint(
            "display_name IS NULL OR display_name ~ '[^[:space:]]'",
            name="ck_queue_entry_optional_name",
        ),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    session_id = db.Column(
        db.Uuid, db.ForeignKey("help_session.id", ondelete="RESTRICT"), nullable=False
    )
    student_identity_id = db.Column(
        db.Uuid, db.ForeignKey("student_identity.id", ondelete="RESTRICT"), nullable=False
    )
    queue_number = db.Column(db.Integer, nullable=False)
    display_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="waiting", server_default="waiting")
    joined_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.clock_timestamp()
    )
    service_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    left_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.clock_timestamp()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.clock_timestamp(),
        onupdate=db.func.clock_timestamp(),
    )
