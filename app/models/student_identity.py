"""Pseudonymous browser profile, never a verified student identity."""

from uuid import uuid4

from app.extensions import db


class StudentIdentity(db.Model):
    __tablename__ = "student_identity"
    __table_args__ = (
        db.Index(
            "uq_student_identity_token_hash",
            "public_token_hash",
            unique=True,
            mssql_where=db.text("public_token_hash IS NOT NULL"),
        ),
        db.CheckConstraint(
            "LEN(public_token_hash) = 64 AND public_token_hash NOT LIKE '%[^0-9a-f]%'",
            name="ck_student_identity_token_hash",
        ),
        db.CheckConstraint("last_seen_at >= first_seen_at", name="ck_student_identity_seen_order"),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid4)
    # Nullable so a future retention policy can unlink a browser while retaining history.
    public_token_hash = db.Column(db.String(64, collation="Latin1_General_100_BIN2"), nullable=True)
    first_seen_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    last_seen_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.sysdatetimeoffset()
    )
