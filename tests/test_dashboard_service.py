from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Defect,
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    Version,
)
from app.services.dashboard_service import build_dashboard


FIXED_NOW = datetime(2026, 7, 11, 12, 0, 0)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "dashboard_service_test.sqlite"
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


def create_execution(test_case, result, days_ago, marker):
    execution = ExecutionRecord(
        result=result,
        actual_result=(
            f"Sample failed result for {marker}." if result == "failed" else ""
        ),
        tester="Demo Dashboard Tester",
        environment="Dashboard Demo Env",
        executed_at=FIXED_NOW - timedelta(days=days_ago),
        notes=f"dashboard-test:{marker}",
    )
    execution.capture_test_case_snapshot(test_case)
    db.session.add(execution)
    db.session.flush()
    return execution


def create_defect(execution, code, status, severity, days_ago):
    defect = Defect(
        code=code,
        title=f"Sample {code} defect",
        description="Sample dashboard defect description.",
        component="Audio",
        severity=severity,
        priority="P1",
        status=status,
        reproduction_steps="Run sample dashboard reproduction steps.",
        observed_result="Sample dashboard observed result.",
        reporter="Demo Dashboard Reporter",
        created_at=FIXED_NOW - timedelta(days=days_ago),
    )
    defect.capture_execution_snapshot(execution)
    db.session.add(defect)
    return defect


@pytest.fixture()
def dashboard_data(app):
    with app.app_context():
        project_a = Project(
            name="Mock Dashboard Project A",
            code="MOCK-DASHBOARD-A",
            status="active",
        )
        project_b = Project(
            name="Mock Dashboard Project B",
            code="MOCK-DASHBOARD-B",
            status="active",
        )
        db.session.add_all([project_a, project_b])
        db.session.flush()

        version_a1 = Version(
            project_id=project_a.id,
            name="Demo Dashboard Version A1",
            code="FW_DEMO_DASH_A1",
            status="testing",
        )
        version_a2 = Version(
            project_id=project_a.id,
            name="Demo Dashboard Version A2",
            code="FW_DEMO_DASH_A2",
            status="planned",
        )
        version_b1 = Version(
            project_id=project_b.id,
            name="Demo Dashboard Version B1",
            code="FW_DEMO_DASH_B1",
            status="testing",
        )
        db.session.add_all([version_a1, version_a2, version_b1])
        db.session.flush()

        case_a1 = ChecklistTestCase(
            version_id=version_a1.id,
            title="Sample Dashboard Audio Case",
            code="TC_DASH_AUDIO",
            module="Audio",
            priority="P1",
            steps="Run sample dashboard audio steps.",
            expected_result="Sample dashboard audio result is stable.",
            status="active",
        )
        archived_case = ChecklistTestCase(
            version_id=version_a1.id,
            title="Sample Archived Dashboard Case",
            code="TC_DASH_ARCHIVED",
            module="Audio",
            priority="P3",
            steps="Run archived sample steps.",
            expected_result="Archived sample result.",
            status="archived",
        )
        case_a2 = ChecklistTestCase(
            version_id=version_a2.id,
            title="Sample Dashboard Bluetooth Case",
            code="TC_DASH_BT",
            module="Bluetooth",
            priority="P2",
            steps="Run sample dashboard Bluetooth steps.",
            expected_result="Sample Bluetooth result is stable.",
            status="active",
        )
        case_b1 = ChecklistTestCase(
            version_id=version_b1.id,
            title="Sample Dashboard Charging Case",
            code="TC_DASH_CHARGE",
            module="Charging",
            priority="P2",
            steps="Run sample dashboard charging steps.",
            expected_result="Sample charging result is stable.",
            status="active",
        )
        db.session.add_all([case_a1, archived_case, case_a2, case_b1])
        db.session.flush()

        create_execution(case_a1, "passed", 1, "a-pass-recent")
        failed_with_defects = create_execution(
            case_a1, "failed", 1, "a-fail-with-defects"
        )
        create_execution(case_a1, "failed", 2, "a-fail-without-defect")
        create_execution(case_a1, "blocked", 3, "a-blocked")
        create_execution(case_a1, "skipped", 4, "a-skipped")
        create_execution(case_a1, "passed", 10, "a-pass-ten-days")
        old_failed = create_execution(case_a1, "failed", 40, "a-old-failed")
        create_execution(case_b1, "passed", 1, "b-pass")
        project_b_failed = create_execution(case_b1, "failed", 1, "b-failed")

        create_defect(failed_with_defects, "DEF_DASH_001", "open", "blocker", 1)
        create_defect(failed_with_defects, "DEF_DASH_002", "fixed", "critical", 1)
        create_defect(old_failed, "DEF_DASH_003", "open", "major", 40)
        create_defect(project_b_failed, "DEF_DASH_004", "closed", "minor", 1)
        create_defect(project_b_failed, "DEF_DASH_005", "rejected", "minor", 1)
        db.session.commit()

        return {
            "project_a": project_a.id,
            "project_b": project_b.id,
            "version_a1": version_a1.id,
            "version_a2": version_a2.id,
            "version_b1": version_b1.id,
        }


def test_empty_dashboard_has_zero_counts_and_undefined_rates(app):
    with app.app_context():
        result = build_dashboard(range_key="30d", now=FIXED_NOW)

    assert result["scope_counts"] == {"projects": 0, "versions": 0, "test_cases": 0}
    assert result["execution"]["total"] == 0
    assert result["execution"]["by_result"] == {
        "passed": 0,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
    }
    assert result["execution"]["pass_rate"] is None
    assert result["execution"]["fail_rate"] is None
    assert result["execution"]["failed_with_defect_rate"] is None


def test_execution_distribution_and_rates_use_passed_plus_failed(
    app, dashboard_data
):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="30d",
            now=FIXED_NOW,
        )

    assert result["execution"]["total"] == 6
    assert result["execution"]["by_result"] == {
        "passed": 2,
        "failed": 2,
        "blocked": 1,
        "skipped": 1,
    }
    assert result["execution"]["pass_rate"] == 50.0
    assert result["execution"]["fail_rate"] == 50.0
    assert result["execution"]["failed_with_defect_rate"] == 50.0


def test_project_and_version_filters_keep_scope_consistent(app, dashboard_data):
    with app.app_context():
        project_result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="30d",
            now=FIXED_NOW,
        )
        version_result = build_dashboard(
            project_id=dashboard_data["project_a"],
            version_id=dashboard_data["version_a2"],
            range_key="30d",
            now=FIXED_NOW,
        )

    assert project_result["scope_counts"] == {
        "projects": 1,
        "versions": 2,
        "test_cases": 2,
    }
    assert project_result["execution"]["total"] == 6
    assert version_result["scope_counts"] == {
        "projects": 1,
        "versions": 1,
        "test_cases": 1,
    }
    assert version_result["execution"]["total"] == 0


def test_time_ranges_filter_execution_metrics(app, dashboard_data):
    with app.app_context():
        seven_days = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="7d",
            now=FIXED_NOW,
        )
        thirty_days = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="30d",
            now=FIXED_NOW,
        )
        all_time = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="all",
            now=FIXED_NOW,
        )

    assert seven_days["execution"]["total"] == 5
    assert thirty_days["execution"]["total"] == 6
    assert all_time["execution"]["total"] == 7


def test_trend_fills_missing_dates_with_zero(app, dashboard_data):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="7d",
            now=FIXED_NOW,
        )

    trend = result["trend"]
    assert trend["labels"][0] == "2026-07-05"
    assert trend["labels"][-1] == "2026-07-11"
    assert len(trend["labels"]) == 7
    assert trend["failed"][trend["labels"].index("2026-07-09")] == 1
    assert trend["failed"][trend["labels"].index("2026-07-11")] == 0


def test_version_quality_includes_versions_without_executions(app, dashboard_data):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="30d",
            now=FIXED_NOW,
        )

    rows = {row["version_id"]: row for row in result["version_quality"]}
    first = rows[dashboard_data["version_a1"]]
    empty = rows[dashboard_data["version_a2"]]
    assert first["executions"] == 6
    assert first["passed"] == 2
    assert first["failed"] == 2
    assert first["blocked"] == 1
    assert first["pass_rate"] == 50.0
    assert first["open_defects"] == 3
    assert first["critical_risks"] == 2
    assert empty["executions"] == 0
    assert empty["pass_rate"] is None


def test_current_defect_risk_ignores_time_range_and_uses_expected_statuses(
    app, dashboard_data
):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="7d",
            now=FIXED_NOW,
        )

    assert result["defects"]["open_count"] == 3
    assert result["defects"]["critical_risk_count"] == 2
    assert result["defects"]["period_new_count"] == 2
    assert result["defects"]["by_status"] == {
        "open": 2,
        "fixed": 1,
        "closed": 0,
        "rejected": 0,
    }


def test_failed_execution_with_multiple_defects_is_counted_once(
    app, dashboard_data
):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="30d",
            now=FIXED_NOW,
        )

    assert result["execution"]["by_result"]["failed"] == 2
    assert result["execution"]["failed_with_defect_count"] == 1
    assert result["execution"]["failed_with_defect_rate"] == 50.0


def test_all_time_new_defects_uses_defect_created_at(app, dashboard_data):
    with app.app_context():
        result = build_dashboard(
            project_id=dashboard_data["project_a"],
            range_key="all",
            now=FIXED_NOW,
        )

    assert result["defects"]["period_new_count"] == 3
