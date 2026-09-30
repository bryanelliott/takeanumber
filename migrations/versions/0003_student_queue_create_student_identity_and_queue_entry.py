"""create student identity and queue entry

Revision ID: 0003_student_queue
Revises: 0002_help_session
Create Date: 2026-09-30 17:47:01.162388

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_student_queue"
down_revision = "0002_help_session"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "student_identity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "public_token_hash ~ '^[0-9a-f]{64}$'", name="ck_student_identity_token_hash"
        ),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="ck_student_identity_seen_order"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_token_hash", name="uq_student_identity_token_hash"),
    )
    op.create_table(
        "queue_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("student_identity_id", sa.Uuid(), nullable=False),
        sa.Column("queue_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="waiting", nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("service_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'waiting' AND service_started_at IS NULL AND completed_at IS NULL "
            "AND left_at IS NULL) OR "
            "(status = 'serving' AND service_started_at IS NOT NULL AND completed_at IS NULL "
            "AND left_at IS NULL) OR "
            "(status = 'completed' AND service_started_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND left_at IS NULL) OR "
            "(status = 'left' AND completed_at IS NULL AND left_at IS NOT NULL)",
            name="ck_queue_entry_state_times",
        ),
        sa.CheckConstraint(
            "display_name IS NULL OR display_name ~ '[^[:space:]]'",
            name="ck_queue_entry_optional_name",
        ),
        sa.CheckConstraint(
            "status IN ('waiting', 'serving', 'completed', 'left')", name="ck_queue_entry_status"
        ),
        sa.CheckConstraint("queue_number >= 1", name="ck_queue_entry_number"),
        sa.CheckConstraint(
            "service_started_at >= joined_at AND completed_at >= service_started_at "
            "AND left_at >= joined_at AND left_at >= service_started_at",
            name="ck_queue_entry_time_order",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["help_session.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["student_identity_id"], ["student_identity.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "queue_number", name="uq_queue_entry_session_number"),
    )
    # Explicit PostgreSQL invariant spanning both active states, independent of services.
    op.create_index(
        "uq_queue_entry_active_identity",
        "queue_entry",
        ["session_id", "student_identity_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('waiting', 'serving')"),
    )


def downgrade():
    op.drop_index("uq_queue_entry_active_identity", table_name="queue_entry")
    op.drop_table("queue_entry")
    op.drop_table("student_identity")
