"""Add LLM experiment generation and review evidence.

Revision ID: d7e2f6a9b301
Revises: c5d8a9e4f2b1
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op


revision = "d7e2f6a9b301"
down_revision = "c5d8a9e4f2b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generation_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_model", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("requirement_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_chars", sa.Integer(), nullable=True),
        sa.Column("output_chars", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("finish_reason", sa.String(80), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("structured_output_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_generation_run_status",
        ),
        sa.CheckConstraint(
            "provider IN ('mock', 'deepseek')",
            name="ck_generation_run_provider",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["test_design_session.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["version.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("session_id", "project_id", "version_id", "provider", "status"):
        op.create_index(f"ix_generation_run_{column}", "generation_run", [column])

    with op.batch_alter_table("test_case_draft") as batch_op:
        batch_op.add_column(sa.Column("generation_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_test_case_draft_generation_run_id",
            "generation_run",
            ["generation_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_test_case_draft_generation_run_id", ["generation_run_id"]
        )

    op.create_table(
        "review_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("before_snapshot_json", sa.Text(), nullable=False),
        sa.Column("after_snapshot_json", sa.Text(), nullable=False),
        sa.Column("score_before", sa.Integer(), nullable=False),
        sa.Column("score_after", sa.Integer(), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=False),
        sa.Column("changed_field_count", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('edit', 'accept', 'reject')", name="ck_review_record_action"
        ),
        sa.CheckConstraint(
            "score_before >= 0 AND score_before <= 100",
            name="ck_review_record_score_before",
        ),
        sa.CheckConstraint(
            "score_after >= 0 AND score_after <= 100",
            name="ck_review_record_score_after",
        ),
        sa.CheckConstraint(
            "changed_field_count >= 0 AND changed_field_count <= 9",
            name="ck_review_record_changed_field_count",
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["test_case_draft.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("draft_id", "reviewer_user_id"):
        op.create_index(f"ix_review_record_{column}", "review_record", [column])
    _check_sqlite_foreign_keys()


def downgrade():
    op.drop_table("review_record")
    with op.batch_alter_table("test_case_draft") as batch_op:
        batch_op.drop_index("ix_test_case_draft_generation_run_id")
        batch_op.drop_constraint(
            "fk_test_case_draft_generation_run_id", type_="foreignkey"
        )
        batch_op.drop_column("generation_run_id")
    op.drop_table("generation_run")
    _check_sqlite_foreign_keys()


def _check_sqlite_foreign_keys():
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Foreign key violations after migration: {violations}")
