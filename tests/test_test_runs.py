from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import (
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    TestRun as AutomationTestRun,
    Version,
)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test_runs_test.sqlite"
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


def create_version(code):
    project = Project(
        name=f"Mock TestRun Project {code}",
        code=f"MOCK-TESTRUN-{code}",
        status="active",
    )
    db.session.add(project)
    db.session.flush()
    version = Version(
        project_id=project.id,
        name=f"Demo TestRun Version {code}",
        code=f"FW_DEMO_TESTRUN_{code}",
        status="testing",
    )
    db.session.add(version)
    db.session.flush()
    return version


def create_test_case(version):
    test_case = ChecklistTestCase(
        version_id=version.id,
        title="Sample Automated Audio TestCase",
        code="TC_AUTO_AUDIO_001",
        module="Audio",
        priority="P1",
        steps="Run sample automated audio steps.",
        expected_result="Sample automated audio result is stable.",
        status="active",
    )
    db.session.add(test_case)
    db.session.flush()
    return test_case


def create_execution(test_case, test_run=None):
    execution = ExecutionRecord(
        test_run_id=test_run.id if test_run else None,
        external_case_key="sample.module::test_audio" if test_run else None,
        duration_seconds=Decimal("1.250") if test_run else None,
        result="passed",
        tester="Demo Automation Runner" if test_run else "Demo Manual Tester",
        environment="Automation Demo Env" if test_run else "Manual Demo Env",
    )
    execution.capture_test_case_snapshot(test_case)
    db.session.add(execution)
    db.session.flush()
    return execution


def test_test_run_schema_has_expected_columns_and_constraints(app):
    with app.app_context():
        inspector = inspect(db.engine)
        columns = {column["name"]: column for column in inspector.get_columns("test_run")}
        unique_constraints = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("test_run")
        }
        foreign_keys = inspector.get_foreign_keys("test_run")
        execution_columns = {
            column["name"]
            for column in inspector.get_columns("test_execution")
        }

    assert set(columns) == {
        "id",
        "version_id",
        "source_type",
        "report_hash",
        "runner",
        "environment",
        "started_at",
        "finished_at",
        "imported_at",
        "created_at",
    }
    assert columns["version_id"]["nullable"] is False
    assert columns["report_hash"]["nullable"] is False
    assert unique_constraints["uq_test_run_version_source_hash"] == (
        "version_id",
        "source_type",
        "report_hash",
    )
    assert foreign_keys[0]["referred_table"] == "version"
    assert foreign_keys[0]["constrained_columns"] == ["version_id"]
    assert {
        "test_run_id",
        "external_case_key",
        "duration_seconds",
    }.issubset(execution_columns)


def test_test_run_requires_version_id(app):
    with app.app_context():
        db.session.add(AutomationTestRun(report_hash="a" * 64))

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_test_run_requires_report_hash(app):
    with app.app_context():
        version = create_version("REQUIRED_HASH")
        db.session.add(AutomationTestRun(version_id=version.id))

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_test_run_defaults_to_junit_xml_and_sets_timestamps(app):
    with app.app_context():
        version = create_version("DEFAULTS")
        test_run = AutomationTestRun(version_id=version.id, report_hash="b" * 64)
        db.session.add(test_run)
        db.session.commit()

        assert test_run.source_type == "junit_xml"
        assert test_run.imported_at is not None
        assert test_run.created_at is not None


def test_same_version_rejects_duplicate_source_and_report_hash(app):
    with app.app_context():
        version = create_version("DUPLICATE")
        db.session.add(
            AutomationTestRun(version_id=version.id, report_hash="c" * 64)
        )
        db.session.commit()

        db.session.add(
            AutomationTestRun(version_id=version.id, report_hash="c" * 64)
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_different_versions_allow_same_report_hash(app):
    with app.app_context():
        first_version = create_version("FIRST")
        second_version = create_version("SECOND")
        db.session.add_all(
            [
                AutomationTestRun(version_id=first_version.id, report_hash="d" * 64),
                AutomationTestRun(version_id=second_version.id, report_hash="d" * 64),
            ]
        )
        db.session.commit()

        assert AutomationTestRun.query.count() == 2


def test_test_execution_can_belong_to_test_run(app):
    with app.app_context():
        version = create_version("AUTOMATED")
        test_case = create_test_case(version)
        test_run = AutomationTestRun(
            version_id=version.id,
            report_hash="e" * 64,
            runner="Demo Automation Runner",
            environment="Automation Demo Env",
        )
        db.session.add(test_run)
        db.session.flush()
        execution = create_execution(test_case, test_run)
        db.session.commit()

        assert execution.test_run is test_run
        assert test_run.executions == [execution]
        assert execution.external_case_key == "sample.module::test_audio"
        assert execution.duration_seconds == Decimal("1.250")
        assert execution.test_case_code_snapshot == "TC_AUTO_AUDIO_001"


def test_manual_test_execution_keeps_test_run_id_null(app):
    with app.app_context():
        version = create_version("MANUAL")
        test_case = create_test_case(version)
        execution = create_execution(test_case)
        db.session.commit()

        assert execution.test_run_id is None
        assert execution.test_run is None
        assert execution.external_case_key is None
        assert execution.duration_seconds is None
