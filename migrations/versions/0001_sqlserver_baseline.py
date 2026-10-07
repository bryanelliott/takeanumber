"""Initial Azure SQL schema; supersedes the retired PostgreSQL chain.

Revision ID: 0001_sqlserver_baseline
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_sqlserver_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instructor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.Unicode(length=200), nullable=False),
        sa.Column(
            "password_hash",
            sa.String(length=255, collation="Latin1_General_100_BIN2"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "LEN((display_name + N'!') COLLATE Latin1_General_100_CI_AS_SC) - 1 <= 100",
            name="ck_instructor_name_length",
        ),
        sa.CheckConstraint(
            "display_name COLLATE Latin1_General_100_BIN2 LIKE (N'%[^' + NCHAR(9) + "
            "NCHAR(10) + NCHAR(11) + NCHAR(12) + NCHAR(13) + NCHAR(28) + NCHAR(29) + "
            "NCHAR(30) + NCHAR(31) + NCHAR(32) + NCHAR(133) + NCHAR(160) + NCHAR(5760) + "
            "NCHAR(8192) + NCHAR(8193) + NCHAR(8194) + NCHAR(8195) + NCHAR(8196) + "
            "NCHAR(8197) + NCHAR(8198) + NCHAR(8199) + NCHAR(8200) + NCHAR(8201) + "
            "NCHAR(8202) + NCHAR(8232) + NCHAR(8233) + NCHAR(8239) + NCHAR(8287) + "
            "NCHAR(12288) + N']%')",
            name="ck_instructor_display_name_required",
        ),
        sa.CheckConstraint("password_hash LIKE 'scrypt:%'", name="ck_instructor_password_hash"),
        sa.CheckConstraint(
            "email COLLATE Latin1_General_100_BIN2 = LOWER(email) AND "
            "DATALENGTH(email) = DATALENGTH(LTRIM(RTRIM(email))) AND LEN(email) > 0",
            name="ck_instructor_email_normalized",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_instructor_email"),
    )
    op.create_table(
        "student_identity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "public_token_hash",
            sa.String(length=64, collation="Latin1_General_100_BIN2"),
            nullable=True,
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "LEN(public_token_hash) = 64 AND public_token_hash NOT LIKE '%[^0-9a-f]%'",
            name="ck_student_identity_token_hash",
        ),
        sa.CheckConstraint("last_seen_at >= first_seen_at", name="ck_student_identity_seen_order"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_student_identity_token_hash",
        "student_identity",
        ["public_token_hash"],
        unique=True,
        mssql_where=sa.text("public_token_hash IS NOT NULL"),
    )
    op.create_table(
        "help_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "public_code", sa.String(length=22, collation="Latin1_General_100_BIN2"), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=16, collation="Latin1_General_100_BIN2"),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_queue_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR (status = 'ended' AND "
            "ended_at IS NOT NULL)",
            name="ck_help_session_ended_state",
        ),
        sa.CheckConstraint(
            "LEN(public_code) = 22 AND public_code NOT LIKE '%[^A-Za-z0-9_-]%'",
            name="ck_help_session_public_code",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'ended') AND DATALENGTH(status) = LEN(status)",
            name="ck_help_session_status",
        ),
        sa.CheckConstraint("ended_at >= started_at", name="ck_help_session_time_order"),
        sa.CheckConstraint("next_queue_number >= 1", name="ck_help_session_next_queue_number"),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_code", name="uq_help_session_public_code"),
    )
    op.create_index(
        "uq_help_session_active_instructor",
        "help_session",
        ["instructor_id"],
        unique=True,
        mssql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "instructor_setting",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), nullable=False),
        sa.Column("alert_next_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "alert_serving_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column(
            "visual_alert_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("sound_alert_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("vibration_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("advance_warning_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "advance_warning_count BETWEEN 1 AND 3", name="ck_instructor_setting_warning_count"
        ),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_id", name="uq_instructor_setting_instructor"),
    )
    op.create_table(
        "queue_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("student_identity_id", sa.Uuid(), nullable=False),
        sa.Column("queue_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.Unicode(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16, collation="Latin1_General_100_BIN2"),
            server_default="waiting",
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column("service_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("sysdatetimeoffset()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "LEN((display_name + N'!') COLLATE Latin1_General_100_CI_AS_SC) - 1 <= 100",
            name="ck_queue_entry_name_length",
        ),
        sa.CheckConstraint(
            "(status = 'waiting' AND service_started_at IS NULL AND completed_at IS "
            "NULL AND left_at IS NULL) OR (status = 'serving' AND service_started_at "
            "IS NOT NULL AND completed_at IS NULL AND left_at IS NULL) OR (status = "
            "'completed' AND service_started_at IS NOT NULL AND completed_at IS NOT "
            "NULL AND left_at IS NULL) OR (status = 'left' AND completed_at IS NULL "
            "AND left_at IS NOT NULL)",
            name="ck_queue_entry_state_times",
        ),
        sa.CheckConstraint(
            "display_name IS NULL OR display_name COLLATE Latin1_General_100_BIN2 LIKE "
            "(N'%[^' + NCHAR(9) + NCHAR(10) + NCHAR(11) + NCHAR(12) + NCHAR(13) + NCHAR(28) "
            "+ NCHAR(29) + NCHAR(30) + NCHAR(31) + NCHAR(32) + NCHAR(133) + NCHAR(160) + "
            "NCHAR(5760) + NCHAR(8192) + NCHAR(8193) + NCHAR(8194) + NCHAR(8195) + "
            "NCHAR(8196) + NCHAR(8197) + NCHAR(8198) + NCHAR(8199) + NCHAR(8200) + "
            "NCHAR(8201) + NCHAR(8202) + NCHAR(8232) + NCHAR(8233) + NCHAR(8239) + "
            "NCHAR(8287) + NCHAR(12288) + N']%')",
            name="ck_queue_entry_optional_name",
        ),
        sa.CheckConstraint(
            "status IN ('waiting', 'serving', 'completed', 'left') "
            "AND DATALENGTH(status) = LEN(status)",
            name="ck_queue_entry_status",
        ),
        sa.CheckConstraint("queue_number >= 1", name="ck_queue_entry_number"),
        sa.CheckConstraint(
            "service_started_at >= joined_at AND completed_at >= service_started_at "
            "AND left_at >= joined_at AND left_at >= service_started_at",
            name="ck_queue_entry_time_order",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["help_session.id"], ondelete="NO ACTION"),
        sa.ForeignKeyConstraint(
            ["student_identity_id"], ["student_identity.id"], ondelete="NO ACTION"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "queue_number", name="uq_queue_entry_session_number"),
    )
    op.create_index(
        "uq_queue_entry_active_identity",
        "queue_entry",
        ["session_id", "student_identity_id"],
        unique=True,
        mssql_where=sa.text("status IN ('waiting', 'serving')"),
    )
    op.create_index(
        "uq_queue_entry_serving_session",
        "queue_entry",
        ["session_id"],
        unique=True,
        mssql_where=sa.text("status = 'serving'"),
    )


def downgrade():
    op.drop_table("queue_entry")
    op.drop_table("instructor_setting")
    op.drop_table("help_session")
    op.drop_table("student_identity")
    op.drop_table("instructor")
