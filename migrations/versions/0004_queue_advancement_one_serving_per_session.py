"""Enforce at most one currently serving request per session.

Revision ID: 0004_queue_advancement
Revises: 0003_student_queue
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_queue_advancement"
down_revision = "0003_student_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "uq_queue_entry_serving_session",
        "queue_entry",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'serving'"),
    )


def downgrade():
    op.drop_index("uq_queue_entry_serving_session", table_name="queue_entry")
