"""create help session

Revision ID: 0002_help_session
Revises: 0001_instructor
Create Date: 2026-09-30 16:28:59.026425

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_help_session"
down_revision = "0001_instructor"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "help_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), nullable=False),
        sa.Column("public_code", sa.String(length=22), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_queue_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_help_session_ended_state",
        ),
        sa.CheckConstraint(
            "public_code ~ '^[A-Za-z0-9_-]{22}$'", name="ck_help_session_public_code"
        ),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_help_session_status"),
        sa.CheckConstraint("ended_at >= started_at", name="ck_help_session_time_order"),
        sa.CheckConstraint("next_queue_number >= 1", name="ck_help_session_next_queue_number"),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_code", name="uq_help_session_public_code"),
    )
    op.create_index(
        "uq_help_session_active_instructor",
        "help_session",
        ["instructor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_index("uq_help_session_active_instructor", table_name="help_session")
    op.drop_table("help_session")
