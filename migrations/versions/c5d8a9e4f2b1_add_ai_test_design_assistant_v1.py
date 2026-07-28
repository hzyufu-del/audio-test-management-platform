"""add AI Test Design Assistant V1

Revision ID: c5d8a9e4f2b1
Revises: 7c9d0e4f6a21
Create Date: 2026-07-26 22:10:00.000000

"""

import sqlalchemy as sa
from alembic import op


revision = "c5d8a9e4f2b1"
down_revision = "7c9d0e4f6a21"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "test_design_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_model", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("test_points_json", sa.Text(), nullable=False),
        sa.Column("limitations_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('mock', 'deepseek')",
            name="ck_test_design_session_provider",
        ),
        sa.CheckConstraint(
            "quality_score >= 0 AND quality_score <= 100",
            name="ck_test_design_session_quality_score",
        ),
        sa.CheckConstraint(
            "status IN "
            "('generated', 'partially_reviewed', 'accepted', 'rejected')",
            name="ck_test_design_session_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(
        "test_design_session",
        schema=None,
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_test_design_session_project_id"),
            ["project_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_test_design_session_provider"),
            ["provider"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_test_design_session_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_test_design_session_version_id"),
            ["version_id"],
            unique=False,
        )

    op.create_table(
        "test_case_draft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("suggested_code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("precondition", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("scenario_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("accepted_test_case_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "("
            "status = 'accepted' AND accepted_test_case_id IS NOT NULL"
            ") OR ("
            "status != 'accepted' AND accepted_test_case_id IS NULL"
            ")",
            name="ck_test_case_draft_accepted_link",
        ),
        sa.CheckConstraint(
            "scenario_type IN "
            "('normal', 'negative', 'boundary', 'compatibility', "
            "'recovery', 'security')",
            name="ck_test_case_draft_scenario_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_test_case_draft_status",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_test_case_id"],
            ["test_case.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["test_design_session.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "accepted_test_case_id",
            name="uq_test_case_draft_accepted_case",
        ),
    )
    with op.batch_alter_table("test_case_draft", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_test_case_draft_session_id"),
            ["session_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_test_case_draft_status"),
            ["status"],
            unique=False,
        )

    _check_sqlite_foreign_keys()


def downgrade():
    with op.batch_alter_table("test_case_draft", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_test_case_draft_status"))
        batch_op.drop_index(batch_op.f("ix_test_case_draft_session_id"))
    op.drop_table("test_case_draft")

    with op.batch_alter_table(
        "test_design_session",
        schema=None,
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_test_design_session_version_id")
        )
        batch_op.drop_index(batch_op.f("ix_test_design_session_status"))
        batch_op.drop_index(batch_op.f("ix_test_design_session_provider"))
        batch_op.drop_index(
            batch_op.f("ix_test_design_session_project_id")
        )
    op.drop_table("test_design_session")

    _check_sqlite_foreign_keys()


def _check_sqlite_foreign_keys():
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    violations = connection.exec_driver_sql(
        "PRAGMA foreign_key_check"
    ).fetchall()
    if violations:
        raise RuntimeError(
            f"Foreign key violations after migration: {violations}"
        )
