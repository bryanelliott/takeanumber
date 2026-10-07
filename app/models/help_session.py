"""Instructor-owned help sessions, without student queue entries."""

from datetime import UTC, datetime
from uuid import uuid4

from app.extensions import db


class HelpSession(db.Model):
    __tablename__ = "help_session"
    __table_args__ = (
        db.UniqueConstraint("public_code", name="uq_help_session_public_code"),
        db.Index(
            "uq_help_session_active_instructor",
            "instructor_id",
            unique=True,
            mssql_where=db.text("status = 'active'"),
        ),
        db.CheckConstraint(
            "status IN ('active', 'ended') AND DATALENGTH(status) = LEN(status)",
            name="ck_help_session_status",
        ),
        db.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_help_session_ended_state",
        ),
        db.CheckConstraint("ended_at >= started_at", name="ck_help_session_time_order"),
        db.CheckConstraint("next_queue_number >= 1", name="ck_help_session_next_queue_number"),
        db.CheckConstraint(
            "LEN(public_code) = 22 AND public_code NOT LIKE '%[^A-Za-z0-9_-]%'",
            name="ck_help_session_public_code",
        ),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    instructor_id = db.Column(
        db.Uuid, db.ForeignKey("instructor.id", ondelete="NO ACTION"), nullable=False
    )
    public_code = db.Column(db.String(22, collation="Latin1_General_100_BIN2"), nullable=False)
    status = db.Column(
        db.String(16, collation="Latin1_General_100_BIN2"),
        nullable=False,
        default="active",
        server_default="active",
    )
    started_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)
    next_queue_number = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.sysdatetimeoffset(),
        onupdate=lambda: datetime.now(UTC),
    )
    instructor = db.relationship("Instructor")

    @property
    def accepts_joins(self):
        """State only; callers must lock/recheck before a future queue mutation."""
        return self.status == "active" and self.ended_at is None
