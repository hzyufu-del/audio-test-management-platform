import json

from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


PREVIOUS_REVISION = "02e4b0712fc4"
LOG_ANALYSIS_REVISION = "7c9d0e4f6a21"


def make_app(tmp_path, filename):
    database_path = tmp_path / filename
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )


def log_schema():
    inspector = inspect(db.engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("log_file")
    }
    constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("log_file")
    }
    return columns, constraints


def test_log_analysis_migration_can_upgrade_downgrade_and_reupgrade(tmp_path):
    app = make_app(tmp_path, "log_migration_cycle.sqlite")
    runner = app.test_cli_runner()

    result = runner.invoke(args=["db", "upgrade", LOG_ANALYSIS_REVISION])
    assert result.exit_code == 0, result.output

    with app.app_context():
        columns, constraints = log_schema()
        assert "analysis_summary" in columns
        assert "storage_path" not in columns
        assert constraints["uq_log_file_project_sha256"] == (
            "project_id",
            "sha256",
        )

    result = runner.invoke(args=["db", "downgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output

    with app.app_context():
        columns, constraints = log_schema()
        assert "analysis_summary" not in columns
        assert "storage_path" in columns
        assert "category" in columns
        assert "uq_log_file_project_sha256" not in constraints

    result = runner.invoke(args=["db", "upgrade", LOG_ANALYSIS_REVISION])
    assert result.exit_code == 0, result.output

    with app.app_context():
        columns, constraints = log_schema()
        assert columns["analysis_summary"]["nullable"] is False
        assert columns["version_id"]["nullable"] is True
        assert constraints["uq_log_file_project_sha256"] == (
            "project_id",
            "sha256",
        )
        assert db.session.execute(
            text("PRAGMA foreign_key_check")
        ).fetchall() == []


def test_log_analysis_migration_backfills_legacy_metadata_without_path(tmp_path):
    app = make_app(tmp_path, "log_migration_backfill.sqlite")
    runner = app.test_cli_runner()

    result = runner.invoke(args=["db", "upgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output

    with app.app_context():
        db.session.execute(
            text(
                """
                INSERT INTO project
                    (id, name, code, description, status, created_at, updated_at)
                VALUES
                    (101, 'Mock Log Migration Project', 'MOCK-LOG-MIGRATION',
                     'Sample migration project.', 'active', CURRENT_TIMESTAMP,
                     CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO version
                    (id, project_id, name, code, description, release_type,
                     status, planned_test_date, created_at, updated_at)
                VALUES
                    (201, 101, 'Demo Log Migration Version',
                     'FW_DEMO_LOG_MIGRATION', 'Sample migration version.',
                     'sample', 'testing', NULL, CURRENT_TIMESTAMP,
                     CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO log_file
                    (id, project_id, version_id, filename, category,
                     storage_path, uploaded_by, notes, uploaded_at)
                VALUES
                    (301, 101, 201, 'sample_legacy.log', 'sample',
                     'C:/private/mock/sample_legacy.log', NULL,
                     'Legacy mock metadata.', CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.commit()
        db.session.remove()

    result = runner.invoke(args=["db", "upgrade", LOG_ANALYSIS_REVISION])
    assert result.exit_code == 0, result.output

    with app.app_context():
        columns, _constraints = log_schema()
        row = db.session.execute(
            text(
                """
                SELECT filename, file_size_bytes, sha256, analysis_status,
                       risk_level, total_lines, critical_count, error_count,
                       warning_count, info_count, analysis_summary, uploaded_by
                FROM log_file
                WHERE id = 301
                """
            )
        ).mappings().one()

        assert "storage_path" not in columns
        assert row["filename"] == "sample_legacy.log"
        assert row["file_size_bytes"] == 0
        assert len(row["sha256"]) == 64
        assert row["analysis_status"] == "legacy_metadata"
        assert row["risk_level"] == "low"
        assert row["total_lines"] == 0
        assert row["critical_count"] == 0
        assert row["error_count"] == 0
        assert row["warning_count"] == 0
        assert row["info_count"] == 0
        assert row["uploaded_by"] == "legacy_demo"
        assert json.loads(row["analysis_summary"])["legacy_metadata"] is True
        assert "C:/private" not in row["analysis_summary"]
