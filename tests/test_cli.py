from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import (
    Defect,
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    User,
    Version,
)


def make_app(tmp_path):
    database_path = tmp_path / "cli_test.sqlite"
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )


def test_init_db_does_not_create_tables_before_migrations(tmp_path):
    app = make_app(tmp_path)

    result = app.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code != 0
    assert "db upgrade" in result.output

    with app.app_context():
        assert inspect(db.engine).get_table_names() == []


def test_init_db_seeds_demo_data_when_schema_exists(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        db.create_all()

    result = app.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code == 0
    assert "mock/demo/sample" in result.output

    with app.app_context():
        assert User.query.filter_by(email="demo@example.com").count() == 1
        assert Project.query.filter_by(code="MOCK-AUDIO-01").count() == 1
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_001").count() == 1
        assert Project.query.count() >= 2
        assert Version.query.count() >= 3
        assert {
            row.result for row in ExecutionRecord.query.all()
        } == {"passed", "failed", "blocked", "skipped"}
        defect = Defect.query.filter_by(code="DEF_DEMO_001").one()
        assert defect.environment_snapshot == "Android Demo Env"
        assert defect.actual_result_snapshot == "Demo failed audio output is recorded."
        assert defect.executed_at_snapshot == defect.execution.executed_at
        assert all(item.execution.result == "failed" for item in Defect.query.all())
        assert {item.status for item in Defect.query.all()} == {
            "open",
            "fixed",
            "closed",
            "rejected",
        }
        assert {item.severity for item in Defect.query.all()} == {
            "blocker",
            "critical",
            "major",
            "minor",
        }
        assert any(len(item.defects) > 1 for item in ExecutionRecord.query.all())
        assert any(
            item.result == "failed" and not item.defects
            for item in ExecutionRecord.query.all()
        )
