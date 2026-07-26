import pytest
from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import Defect, Project, TestCase, TestExecution, Version


@pytest.fixture()
def api_app(tmp_path):
    database_path = tmp_path / "api_v1_test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "WTF_CSRF_ENABLED": False,
        }
    )

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def api_client(api_app):
    return api_app.test_client()


@pytest.fixture()
def api_catalog(api_app):
    with api_app.app_context():
        first_project = Project(
            name="Mock API Audio Project",
            code="MOCK-API-AUDIO",
            description="Sample project for REST API tests.",
            status="active",
        )
        second_project = Project(
            name="Demo API Secondary Project",
            code="DEMO-API-SECONDARY",
            description="Mock secondary project for filter tests.",
            status="active",
        )
        db.session.add_all((first_project, second_project))
        db.session.flush()

        first_version = Version(
            project_id=first_project.id,
            name="Demo API Firmware Alpha",
            code="FW_DEMO_API_ALPHA",
            description="Sample primary API version.",
            status="testing",
        )
        second_version = Version(
            project_id=first_project.id,
            name="Demo API Firmware Beta",
            code="FW_DEMO_API_BETA",
            description="Sample alternate API version.",
            status="planned",
        )
        other_version = Version(
            project_id=second_project.id,
            name="Sample API Firmware Gamma",
            code="FW_SAMPLE_API_GAMMA",
            description="Mock cross-project API version.",
            status="testing",
        )
        db.session.add_all((first_version, second_version, other_version))
        db.session.flush()

        first_case = TestCase(
            version_id=first_version.id,
            code="TC_AUDIO_API_001",
            title="Sample Audio Playback API Case",
            module="Audio",
            priority="P1",
            case_type="checklist",
            precondition="Use mock audio state.",
            steps="Run sample playback steps.",
            expected_result="Sample playback succeeds.",
            status="active",
        )
        second_case = TestCase(
            version_id=first_version.id,
            code="TC_BT_API_002",
            title="Demo Bluetooth Reconnect API Case",
            module="Bluetooth",
            priority="P2",
            case_type="checklist",
            precondition=None,
            steps="Run demo reconnect steps.",
            expected_result="Demo reconnect succeeds.",
            status="draft",
        )
        other_case = TestCase(
            version_id=other_version.id,
            code="TC_CHARGING_API_003",
            title="Mock Charging Status API Case",
            module="Charging",
            priority="P3",
            case_type="checklist",
            precondition="Use sample charging state.",
            steps="Run mock charging steps.",
            expected_result="Mock charging status is shown.",
            status="archived",
        )
        stable_case_timestamp = datetime(
            2026,
            7,
            20,
            12,
            0,
            tzinfo=timezone.utc,
        )
        for test_case in (first_case, second_case, other_case):
            test_case.created_at = stable_case_timestamp
            test_case.updated_at = stable_case_timestamp
        db.session.add_all((first_case, second_case, other_case))
        db.session.commit()

        return {
            "first_project_id": first_project.id,
            "second_project_id": second_project.id,
            "first_version_id": first_version.id,
            "second_version_id": second_version.id,
            "other_version_id": other_version.id,
            "first_case_id": first_case.id,
            "second_case_id": second_case.id,
            "other_case_id": other_case.id,
        }


@pytest.fixture()
def api_executions(api_app, api_catalog):
    with api_app.app_context():
        first_case = db.session.get(TestCase, api_catalog["first_case_id"])
        second_case = db.session.get(TestCase, api_catalog["second_case_id"])
        other_case = db.session.get(TestCase, api_catalog["other_case_id"])

        passed = TestExecution(
            result="passed",
            actual_result=None,
            tester="Demo API Tester A",
            environment="Android Demo Env",
            executed_at=datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc),
            notes="Sample passed execution.",
        )
        passed.capture_test_case_snapshot(first_case)

        failed = TestExecution(
            result="failed",
            actual_result="Sample reconnect remained unavailable.",
            tester="Demo API Tester B",
            environment="Android Sample Env",
            executed_at=datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc),
            notes="Mock failed execution.",
        )
        failed.capture_test_case_snapshot(second_case)

        blocked = TestExecution(
            result="blocked",
            actual_result="Mock fixture was unavailable.",
            tester="Sample API Tester C",
            environment="Firmware Demo Env",
            executed_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
            notes="Demo blocked execution.",
        )
        blocked.capture_test_case_snapshot(other_case)

        db.session.add_all((passed, failed, blocked))
        db.session.flush()

        defect = Defect(
            code="DEF_API_EXECUTION_SUMMARY",
            title="Sample execution summary defect",
            description="Mock defect used by execution detail tests.",
            component="Bluetooth",
            severity="major",
            priority="P1",
            status="open",
            reproduction_steps="Run sample reconnect steps.",
            observed_result="Sample reconnect remained unavailable.",
            reporter="Demo API Tester B",
        )
        defect.capture_execution_snapshot(failed)
        db.session.add(defect)
        db.session.commit()

        return {
            "passed_id": passed.id,
            "failed_id": failed.id,
            "blocked_id": blocked.id,
            "defect_id": defect.id,
        }


@pytest.fixture()
def api_defects(api_app, api_catalog, api_executions):
    with api_app.app_context():
        open_defect = db.session.get(
            Defect,
            api_executions["defect_id"],
        )
        failed = db.session.get(
            TestExecution,
            api_executions["failed_id"],
        )
        other_case = db.session.get(
            TestCase,
            api_catalog["other_case_id"],
        )
        other_failed = TestExecution(
            result="failed",
            actual_result="Mock charging state was unavailable.",
            tester="Sample Defect Tester",
            environment="Charging Demo Env",
            executed_at=datetime(2026, 7, 23, 11, 0, tzinfo=timezone.utc),
            notes="Sample cross-project failed execution.",
        )
        other_failed.capture_test_case_snapshot(other_case)
        db.session.add(other_failed)
        db.session.flush()

        fixed = Defect(
            code="DEF_API_FIXED_002",
            title="Demo fixed reconnect defect",
            description="Sample fixed issue for API filter tests.",
            component="Audio",
            severity="critical",
            priority="P0",
            status="fixed",
            reproduction_steps="Run demo reconnect validation.",
            observed_result="Mock reconnect initially failed.",
            reporter="Demo API Reporter",
            assignee="Sample API Assignee",
            resolution="firmware_update",
            resolution_note="Sample firmware update resolved the issue.",
        )
        fixed.capture_execution_snapshot(failed)

        rejected = Defect(
            code="DEF_API_REJECTED_003",
            title="Mock charging observation",
            description="Demo rejected issue for cross-project filtering.",
            component="Charging",
            severity="minor",
            priority="P3",
            status="rejected",
            reproduction_steps="Run sample charging observation.",
            observed_result="Mock charging state was unavailable.",
            reporter="Sample API Reporter",
            resolution_note="Sample evidence did not reproduce.",
        )
        rejected.capture_execution_snapshot(other_failed)
        open_defect.created_at = datetime(
            2026,
            7,
            20,
            12,
            0,
            tzinfo=timezone.utc,
        )
        fixed.created_at = datetime(
            2026,
            7,
            21,
            12,
            0,
            tzinfo=timezone.utc,
        )
        rejected.created_at = datetime(
            2026,
            7,
            22,
            12,
            0,
            tzinfo=timezone.utc,
        )
        db.session.add_all((fixed, rejected))
        db.session.commit()

        return {
            "open_id": api_executions["defect_id"],
            "fixed_id": fixed.id,
            "rejected_id": rejected.id,
            "other_failed_id": other_failed.id,
        }
