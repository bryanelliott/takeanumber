"""Create and backfill instructor alert settings.

Revision ID: 0005_instructor_settings
Revises: 0004_queue_advancement
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0005_instructor_settings"
down_revision = "0004_queue_advancement"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "instructor_setting",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), nullable=False),
        sa.Column("alert_next_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("alert_serving_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("visual_alert_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sound_alert_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("vibration_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("advance_warning_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("instructor_id", name="uq_instructor_setting_instructor"),
        sa.CheckConstraint(
            "advance_warning_count BETWEEN 1 AND 3", name="ck_instructor_setting_warning_count"
        ),
    )
    connection = op.get_bind()
    for instructor_id in connection.execute(sa.text("SELECT id FROM instructor")).scalars():
        connection.execute(table.insert().values(id=uuid4(), instructor_id=instructor_id))


def downgrade():
    op.drop_table("instructor_setting")
