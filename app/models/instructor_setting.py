"""Instructor-owned alert preferences; browser consent remains separate."""

from datetime import UTC, datetime
from uuid import uuid4

from app.extensions import db


class InstructorSetting(db.Model):
    __tablename__ = "instructor_setting"
    __table_args__ = (
        db.UniqueConstraint("instructor_id", name="uq_instructor_setting_instructor"),
        db.CheckConstraint(
            "advance_warning_count BETWEEN 1 AND 3", name="ck_instructor_setting_warning_count"
        ),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    instructor_id = db.Column(
        db.Uuid, db.ForeignKey("instructor.id", ondelete="CASCADE"), nullable=False
    )
    alert_next_enabled = db.Column(db.Boolean, nullable=False, server_default=db.true())
    alert_serving_enabled = db.Column(db.Boolean, nullable=False, server_default=db.true())
    visual_alert_enabled = db.Column(db.Boolean, nullable=False, server_default=db.true())
    sound_alert_enabled = db.Column(db.Boolean, nullable=False, server_default=db.true())
    vibration_enabled = db.Column(db.Boolean, nullable=False, server_default=db.true())
    advance_warning_count = db.Column(db.Integer, nullable=False, server_default="1")
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.sysdatetimeoffset(),
        onupdate=lambda: datetime.now(UTC),
    )
