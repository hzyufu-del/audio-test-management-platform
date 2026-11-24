"""Add nullable Web request identity and safe validation diagnostics.

Revision ID: e8f3a7c1d902
Revises: d7e2f6a9b301
"""

from alembic import op
import sqlalchemy as sa


revision = "e8f3a7c1d902"
down_revision = "d7e2f6a9b301"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_design_session", sa.Column("review_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("test_case_draft", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    # Additive columns/indexes avoid rebuilding or rewriting historical run rows.
    op.add_column("generation_run", sa.Column("request_key", sa.String(128)))
    op.add_column("generation_run", sa.Column("request_fingerprint", sa.String(64)))
    op.add_column("generation_run", sa.Column("active_request_scope", sa.String(64)))
    op.add_column("generation_run", sa.Column("validation_summary_json", sa.Text()))
    op.create_index("uq_generation_run_request_key", "generation_run", ["request_key"], unique=True)
    op.create_index("uq_generation_run_active_scope", "generation_run", ["active_request_scope"], unique=True)


def downgrade():
    raise RuntimeError("Generation evidence downgrade is intentionally unsupported.")
