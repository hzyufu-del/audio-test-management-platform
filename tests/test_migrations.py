from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


PREVIOUS_REVISION = "5013098feed9"


def make_app(tmp_path, filename):
    database_path = tmp_path / filename
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )


def test_migration_upgrade_creates_consistent_schema(tmp_path):
    app = make_app(tmp_path, "migration_schema.sqlite")

    result = app.test_cli_runner().invoke(args=["db", "upgrade"])

    assert result.exit_code == 0, result.output

    with app.app_context():
        inspector = inspect(db.engine)
        test_case_columns = {
            column["name"]: column for column in inspector.get_columns("test_case")
        }
        execution_columns = {
            column["name"]: column for column in inspector.get_columns("test_execution")
        }
        test_case_indexes = {index["name"] for index in inspector.get_indexes("test_case")}
        execution_indexes = {
            index["name"] for index in inspector.get_indexes("test_execution")
        }

        assert "project_id" not in test_case_columns
        assert "is_active" not in test_case_columns
        assert test_case_columns["steps"]["nullable"] is False
        assert test_case_columns["expected_result"]["nullable"] is False
        assert "version_id" not in execution_columns
        assert execution_columns["test_case_code_snapshot"]["nullable"] is False
        assert execution_columns["test_case_title_snapshot"]["nullable"] is False
        assert execution_columns["steps_snapshot"]["nullable"] is False
        assert execution_columns["expected_result_snapshot"]["nullable"] is False
        assert "ix_test_case_status" in test_case_indexes
        assert {
            "ix_test_execution_test_case_id",
            "ix_test_execution_result",
            "ix_test_execution_executed_at",
        } <= execution_indexes


def test_migration_backfills_existing_mock_execution_snapshots(tmp_path):
    app = make_app(tmp_path, "migration_backfill.sqlite")
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
                    (101, 'Mock Migration Project', 'MOCK-MIGRATION-PROJECT',
                     'Sample migration project.', 'active', CURRENT_TIMESTAMP,
                     CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO version
                    (id, project_id, name, code, description, release_type, status,
                     planned_test_date, created_at, updated_at)
                VALUES
                    (201, 101, 'Demo Migration Version', 'FW_DEMO_MIGRATION',
                     'Sample migration version.', 'sample', 'planning', NULL,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO test_case
                    (id, project_id, version_id, title, code, module, priority,
                     case_type, precondition, steps, expected_result, status,
                     is_active, created_at, updated_at)
                VALUES
                    (301, 101, 201, 'Sample Migration TestCase',
                     'TC_AUDIO_MIGRATION', 'Audio', 'P1', 'checklist',
                     'Use mock migration preconditions.',
                     'Run sample migration steps.',
                     'Sample migration result is recorded.', 'active', 1,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.execute(
            text(
                """
                INSERT INTO test_execution
                    (id, test_case_id, version_id, result, actual_result, tester,
                     environment, executed_at, notes, created_at, updated_at)
                VALUES
                    (401, 301, 201, 'passed', 'Demo migration actual result.',
                     'Demo Tester', 'Migration Demo Env', CURRENT_TIMESTAMP,
                     'Sample migration execution.', CURRENT_TIMESTAMP,
                     CURRENT_TIMESTAMP)
                """
            )
        )
        db.session.commit()
        db.session.remove()

    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output

    with app.app_context():
        row = db.session.execute(
            text(
                """
                SELECT test_case_code_snapshot, test_case_title_snapshot,
                       precondition_snapshot, steps_snapshot,
                       expected_result_snapshot
                FROM test_execution
                WHERE id = 401
                """
            )
        ).mappings().one()
        version_status = db.session.execute(
            text("SELECT status FROM version WHERE id = 201")
        ).scalar_one()

        assert row == {
            "test_case_code_snapshot": "TC_AUDIO_MIGRATION",
            "test_case_title_snapshot": "Sample Migration TestCase",
            "precondition_snapshot": "Use mock migration preconditions.",
            "steps_snapshot": "Run sample migration steps.",
            "expected_result_snapshot": "Sample migration result is recorded.",
        }
        assert version_status == "planned"
        assert db.session.execute(text("SELECT COUNT(*) FROM test_case")).scalar_one() == 1
        assert db.session.execute(text("SELECT COUNT(*) FROM test_execution")).scalar_one() == 1
