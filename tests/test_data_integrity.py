import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import (
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    Version,
)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "data_integrity_test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


def create_project_and_version():
    project = Project(
        name="Mock Integrity Project",
        code="MOCK-INTEGRITY-PROJECT",
        description="Sample project for database integrity tests.",
        status="active",
    )
    db.session.add(project)
    db.session.flush()

    version = Version(
        project_id=project.id,
        name="Demo Integrity Version",
        code="FW_DEMO_INTEGRITY",
        description="Sample version for database integrity tests.",
        status="planned",
    )
    db.session.add(version)
    db.session.commit()
    return project, version


def make_test_case(version_id):
    return ChecklistTestCase(
        version_id=version_id,
        title="Sample Integrity TestCase",
        code="TC_AUDIO_INTEGRITY",
        module="Audio",
        priority="P1",
        precondition="Use a mock audio device state.",
        steps="Run sample integrity steps.",
        expected_result="Sample integrity result is recorded.",
        status="active",
    )


def set_legacy_parent_fields(record, **values):
    for name, value in values.items():
        if name in record.__table__.columns:
            setattr(record, name, value)


def set_execution_snapshots(execution):
    snapshots = {
        "test_case_code_snapshot": "TC_AUDIO_ORPHAN",
        "test_case_title_snapshot": "Sample Orphan TestCase",
        "precondition_snapshot": "Use mock preconditions.",
        "steps_snapshot": "Run sample orphan steps.",
        "expected_result_snapshot": "Sample orphan result is recorded.",
    }
    for name, value in snapshots.items():
        if name in execution.__table__.columns:
            setattr(execution, name, value)


def test_sqlite_foreign_keys_are_enabled(app):
    with app.app_context():
        enabled = db.session.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1


def test_database_rejects_test_case_with_missing_version(app):
    with app.app_context():
        project = Project(
            name="Mock Orphan TestCase Project",
            code="MOCK-ORPHAN-TESTCASE",
            status="active",
        )
        db.session.add(project)
        db.session.commit()

        test_case = make_test_case(version_id=999999)
        set_legacy_parent_fields(test_case, project_id=project.id)
        db.session.add(test_case)

        with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
            db.session.commit()

        db.session.rollback()
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_INTEGRITY").count() == 0


def test_database_rejects_execution_with_missing_test_case(app):
    with app.app_context():
        _, version = create_project_and_version()
        execution = ExecutionRecord(
            test_case_id=999999,
            result="passed",
            tester="Demo Tester",
        )
        set_legacy_parent_fields(execution, version_id=version.id)
        set_execution_snapshots(execution)
        db.session.add(execution)

        with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
            db.session.commit()

        db.session.rollback()
        assert ExecutionRecord.query.count() == 0


def test_test_case_gets_project_only_through_version(app):
    with app.app_context():
        project, version = create_project_and_version()
        test_case = make_test_case(version.id)
        set_legacy_parent_fields(test_case, project_id=project.id)
        db.session.add(test_case)
        db.session.commit()

        assert "project_id" not in ChecklistTestCase.__table__.columns
        assert test_case.version.project is project


def test_execution_gets_version_and_project_only_through_test_case(app):
    with app.app_context():
        project, version = create_project_and_version()
        test_case = make_test_case(version.id)
        set_legacy_parent_fields(test_case, project_id=project.id)
        db.session.add(test_case)
        db.session.flush()

        execution = ExecutionRecord(
            test_case_id=test_case.id,
            result="passed",
            tester="Demo Tester",
        )
        set_legacy_parent_fields(execution, version_id=version.id)
        set_execution_snapshots(execution)
        db.session.add(execution)
        db.session.commit()

        assert "version_id" not in ExecutionRecord.__table__.columns
        assert execution.testcase.version is version
        assert execution.testcase.version.project is project
