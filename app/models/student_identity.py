"""Pseudonymous browser profile, never a verified student identity."""

from uuid import uuid4

from app.extensions import db


class StudentIdentity(db.Model):
    __tablename__ = "student_identity"
    __table_args__ = (
        db.UniqueConstraint("public_token_hash", name="uq_student_identity_token_hash"),
        db.CheckConstraint(
            "public_token_hash ~ '^[0-9a-f]{64}$'", name="ck_student_identity_token_hash"
        ),
        db.CheckConstraint("last_seen_at >= first_seen_at", name="ck_student_identity_seen_order"),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    # Nullable so a future retention policy can unlink a browser while retaining history.
    public_token_hash = db.Column(db.String(64), nullable=True)
    first_seen_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.clock_timestamp()
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.clock_timestamp()
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.clock_timestamp()
    )
