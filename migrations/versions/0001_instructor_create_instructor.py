"""create instructor

Revision ID: 0001_instructor
Revises:
Create Date: 2026-09-30 15:56:04.076163

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_instructor"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instructor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "display_name ~ '[^[:space:]]'", name="ck_instructor_display_name_required"
        ),
        sa.CheckConstraint("password_hash LIKE 'scrypt:%'", name="ck_instructor_password_hash"),
        sa.CheckConstraint(
            "email = lower(email) AND email = btrim(email) AND length(email) > 0",
            name="ck_instructor_email_normalized",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_instructor_email"),
    )


def downgrade():
    op.drop_table("instructor")
