"""A historical help request belonging to a browser profile and session."""

from uuid import uuid4

from app.extensions import db

ACTIVE_STATUSES = ("waiting", "serving")


class QueueEntry(db.Model):
    __tablename__ = "queue_entry"
    __table_args__ = (
        db.CheckConstraint(
            "LEN((display_name + N'!') COLLATE Latin1_General_100_CI_AS_SC) - 1 <= 100",
            name="ck_queue_entry_name_length",
        ),
        db.UniqueConstraint("session_id", "queue_number", name="uq_queue_entry_session_number"),
        db.Index(
            "uq_queue_entry_serving_session",
            "session_id",
            unique=True,
            mssql_where=db.text("status = 'serving'"),
        ),
        db.Index(
            "uq_queue_entry_active_identity",
            "session_id",
            "student_identity_id",
            unique=True,
            mssql_where=db.text("status IN ('waiting', 'serving')"),
        ),
        db.CheckConstraint("queue_number >= 1", name="ck_queue_entry_number"),
        db.CheckConstraint(
            "status IN ('waiting', 'serving', 'completed', 'left') "
            "AND DATALENGTH(status) = LEN(status)",
            name="ck_queue_entry_status",
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
            "display_name IS NULL OR display_name COLLATE Latin1_General_100_BIN2 LIKE "
            "(N'%[^' + NCHAR(9) + NCHAR(10) + NCHAR(11) + NCHAR(12) + NCHAR(13) + NCHAR(28) "
            "+ NCHAR(29) + NCHAR(30) + NCHAR(31) + NCHAR(32) + NCHAR(133) + NCHAR(160) + "
            "NCHAR(5760) + NCHAR(8192) + NCHAR(8193) + NCHAR(8194) + NCHAR(8195) + "
            "NCHAR(8196) + NCHAR(8197) + NCHAR(8198) + NCHAR(8199) + NCHAR(8200) + "
            "NCHAR(8201) + NCHAR(8202) + NCHAR(8232) + NCHAR(8233) + NCHAR(8239) + "
            "NCHAR(8287) + NCHAR(12288) + N']%')",
            name="ck_queue_entry_optional_name",
        ),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    session_id = db.Column(
        db.Uuid, db.ForeignKey("help_session.id", ondelete="NO ACTION"), nullable=False
    )
    student_identity_id = db.Column(
        db.Uuid, db.ForeignKey("student_identity.id", ondelete="NO ACTION"), nullable=False
    )
    queue_number = db.Column(db.Integer, nullable=False)
    display_name = db.Column(db.Unicode(200), nullable=True)
    status = db.Column(
        db.String(16, collation="Latin1_General_100_BIN2"),
        nullable=False,
        default="waiting",
        server_default="waiting",
    )
    joined_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    service_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    left_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.sysdatetimeoffset(),
        onupdate=db.func.sysdatetimeoffset(),
    )
