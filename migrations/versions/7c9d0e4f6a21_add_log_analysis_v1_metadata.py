"""add Log Analysis V1 metadata

Revision ID: 7c9d0e4f6a21
Revises: 02e4b0712fc4
Create Date: 2026-07-26 13:30:00.000000

"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op


revision = "7c9d0e4f6a21"
down_revision = "02e4b0712fc4"
branch_labels = None
depends_on = None


def set_sqlite_foreign_keys(enabled):
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return

    value = "ON" if enabled else "OFF"
    with op.get_context().autocommit_block():
        connection.exec_driver_sql(f"PRAGMA foreign_keys={value}")


def check_sqlite_foreign_keys():
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


def legacy_summary_json():
    return json.dumps(
        {
            "schema_version": 1,
            "legacy_metadata": True,
            "total_lines": 0,
            "levels": {
                "critical": 0,
                "error": 0,
                "warning": 0,
                "info": 0,
            },
            "risk_level": "low",
            "domains": {
                "connection": 0,
                "power": 0,
                "battery": 0,
                "audio": 0,
                "protocol": 0,
            },
            "findings": [],
            "findings_truncated": False,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def upgrade():
    set_sqlite_foreign_keys(False)

    with op.batch_alter_table("log_file", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("file_size_bytes", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("sha256", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "analysis_status",
                sa.String(length=30),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("risk_level", sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column("total_lines", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("critical_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("error_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("warning_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("info_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("analysis_summary", sa.Text(), nullable=True)
        )

    connection = op.get_bind()
    legacy_rows = connection.execute(
        sa.text(
            """
            SELECT id, project_id, filename
            FROM log_file
            ORDER BY id
            """
        )
    ).mappings()
    for row in legacy_rows:
        digest_source = (
            f"legacy-log-metadata:{row['project_id']}:{row['id']}:"
            f"{row['filename']}"
        )
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text(
                """
                UPDATE log_file
                SET file_size_bytes = 0,
                    sha256 = :sha256,
                    analysis_status = 'legacy_metadata',
                    risk_level = 'low',
                    total_lines = 0,
                    critical_count = 0,
                    error_count = 0,
                    warning_count = 0,
                    info_count = 0,
                    analysis_summary = :analysis_summary,
                    uploaded_by = COALESCE(uploaded_by, 'legacy_demo')
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "sha256": digest,
                "analysis_summary": legacy_summary_json(),
            },
        )

    with op.batch_alter_table("log_file", schema=None) as batch_op:
        batch_op.alter_column(
            "file_size_bytes",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "sha256",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.alter_column(
            "analysis_status",
            existing_type=sa.String(length=30),
            nullable=False,
        )
        batch_op.alter_column(
            "risk_level",
            existing_type=sa.String(length=20),
            nullable=False,
        )
        batch_op.alter_column(
            "total_lines",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "critical_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "error_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "warning_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "info_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "analysis_summary",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "uploaded_by",
            existing_type=sa.String(length=80),
            nullable=False,
        )
        batch_op.drop_column("storage_path")
        batch_op.drop_column("category")
        batch_op.create_unique_constraint(
            "uq_log_file_project_sha256",
            ["project_id", "sha256"],
        )

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()


def downgrade():
    set_sqlite_foreign_keys(False)

    with op.batch_alter_table("log_file", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_log_file_project_sha256",
            type_="unique",
        )
        batch_op.add_column(
            sa.Column(
                "category",
                sa.String(length=60),
                nullable=False,
                server_default="sample",
            )
        )
        batch_op.add_column(
            sa.Column(
                "storage_path",
                sa.String(length=255),
                nullable=True,
            )
        )
        batch_op.alter_column(
            "uploaded_by",
            existing_type=sa.String(length=80),
            nullable=True,
        )
        batch_op.drop_column("analysis_summary")
        batch_op.drop_column("info_count")
        batch_op.drop_column("warning_count")
        batch_op.drop_column("error_count")
        batch_op.drop_column("critical_count")
        batch_op.drop_column("total_lines")
        batch_op.drop_column("risk_level")
        batch_op.drop_column("analysis_status")
        batch_op.drop_column("sha256")
        batch_op.drop_column("file_size_bytes")

    set_sqlite_foreign_keys(True)
    check_sqlite_foreign_keys()
