from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models import (
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    TestRun as AutomationTestRun,
    Version,
)
from app.services.junit_import_service import (
    JUnitImportPersistenceError,
    JUnitImportService,
    JUnitImportValidationError,
)
from app.services.junit_xml_parser import JUnitXmlParser


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "junit"
FIXED_IMPORTED_AT = datetime(2026, 7, 12, 6, 0, 0, tzinfo=timezone.utc)
SAMPLE_CODES = (
    "TC_SAMPLE_AUDIO_001",
    "TC_SAMPLE_AUDIO_002",
    "TC_SAMPLE_AUDIO_003",
    "TC_SAMPLE_AUDIO_004",
    "TC_SAMPLE_CODEC_001",
)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "junit_import_test.sqlite"
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


def fixture_report(name="sample_results.xml"):
    return JUnitXmlParser().parse((FIXTURE_DIR / name).read_bytes())


def inline_report(testcases, suite_timestamp=None):
    timestamp = f' timestamp="{suite_timestamp}"' if suite_timestamp else ""
    xml = f'<testsuite name="sample-import"{timestamp}>{testcases}</testsuite>'
    return JUnitXmlParser().parse(xml.encode("utf-8"))


def seed_version(suffix, codes=SAMPLE_CODES):
    project = Project(
        name=f"Mock Import Project {suffix}",
        code=f"MOCK-IMPORT-{suffix}",
        status="active",
    )
    db.session.add(project)
    db.session.flush()
    version = Version(
        project_id=project.id,
        name=f"Demo Import Version {suffix}",
        code=f"FW_DEMO_IMPORT_{suffix}",
        status="testing",
    )
    db.session.add(version)
    db.session.flush()

    test_cases = {}
    for index, code in enumerate(codes, start=1):
        test_case = ChecklistTestCase(
            version_id=version.id,
            title=f"Sample Imported TestCase {index}",
            code=code,
            module="Audio",
            priority="P1",
            precondition=f"Sample precondition {index}.",
            steps=f"Run sample import steps {index}.",
            expected_result=f"Sample import result {index} is stable.",
            status="active",
        )
        db.session.add(test_case)
        db.session.flush()
        test_cases[code] = test_case
    db.session.commit()
    return version, test_cases


def import_report(report, version_id, **overrides):
    return JUnitImportService().import_report(
        parsed_report=report,
        version_id=version_id,
        runner=overrides.get("runner", "Demo Automation Runner"),
        environment=overrides.get("environment", "Automation Demo Env"),
        imported_at=overrides.get("imported_at", FIXED_IMPORTED_AT),
    )


def test_import_creates_one_test_run_and_one_execution_per_case(app):
    report = fixture_report()
    with app.app_context():
        version, _ = seed_version("BASIC")
        result = import_report(report, version.id)

        assert result.status == "imported"
        assert result.total_count == 4
        assert result.imported_count == 4
        assert len(result.execution_ids) == 4
        assert AutomationTestRun.query.count() == 1
        assert ExecutionRecord.query.count() == 4


@pytest.mark.parametrize(
    ("code", "expected_result"),
    [
        ("TC_SAMPLE_AUDIO_001", "passed"),
        ("TC_SAMPLE_AUDIO_002", "failed"),
        ("TC_SAMPLE_AUDIO_003", "failed"),
        ("TC_SAMPLE_AUDIO_004", "skipped"),
    ],
)
def test_import_maps_normalized_results(app, code, expected_result):
    with app.app_context():
        version, test_cases = seed_version(f"RESULT-{code[-3:]}")
        import_report(fixture_report(), version.id)

        execution = ExecutionRecord.query.filter_by(
            test_case_id=test_cases[code].id
        ).one()
        assert execution.result == expected_result


def test_error_is_failed_and_preserves_short_raw_type_note(app):
    with app.app_context():
        version, test_cases = seed_version("ERROR")
        import_report(fixture_report(), version.id)

        execution = ExecutionRecord.query.filter_by(
            test_case_id=test_cases["TC_SAMPLE_AUDIO_003"].id
        ).one()
        assert execution.result == "failed"
        assert "raw_result=error" in execution.notes
        assert "RuntimeError: Sample recovery setup error" in execution.actual_result


def test_execution_relations_and_test_case_snapshots_are_set(app):
    with app.app_context():
        version, test_cases = seed_version("RELATIONS")
        result = import_report(fixture_report(), version.id)
        run = db.session.get(AutomationTestRun, result.test_run_id)
        execution = ExecutionRecord.query.filter_by(
            test_case_id=test_cases["TC_SAMPLE_AUDIO_001"].id
        ).one()

        assert execution.test_run is run
        assert execution.testcase is test_cases["TC_SAMPLE_AUDIO_001"]
        assert execution.test_case_code_snapshot == "TC_SAMPLE_AUDIO_001"
        assert execution.test_case_title_snapshot == "Sample Imported TestCase 1"
        assert execution.precondition_snapshot == "Sample precondition 1."
        assert execution.steps_snapshot == "Run sample import steps 1."
        assert execution.expected_result_snapshot == "Sample import result 1 is stable."


def test_runner_environment_duration_and_timestamp_are_mapped(app):
    with app.app_context():
        version, test_cases = seed_version("METADATA")
        import_report(fixture_report(), version.id)
        execution = ExecutionRecord.query.filter_by(
            test_case_id=test_cases["TC_SAMPLE_AUDIO_001"].id
        ).one()

        assert execution.tester == "Demo Automation Runner"
        assert execution.environment == "Automation Demo Env"
        assert execution.duration_seconds == Decimal("1.250")
        assert execution.executed_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 7, 12, 1, 1, tzinfo=timezone.utc
        )


def test_missing_timestamp_uses_fixed_imported_at(app):
    report = inline_report(
        '<testcase name="sample_without_time"><properties>'
        '<property name="platform_test_case_code" value="TC_SAMPLE_AUDIO_001" />'
        "</properties></testcase>"
    )
    with app.app_context():
        version, _ = seed_version("NO-TIMESTAMP")
        import_report(report, version.id)
        execution = ExecutionRecord.query.one()

        assert execution.executed_at.replace(tzinfo=timezone.utc) == FIXED_IMPORTED_AT


def test_parameterized_results_create_multiple_executions_for_one_test_case(app):
    with app.app_context():
        version, test_cases = seed_version("PARAMETERIZED")
        result = import_report(fixture_report("parameterized_duplicates.xml"), version.id)

        executions = ExecutionRecord.query.filter_by(
            test_case_id=test_cases["TC_SAMPLE_CODEC_001"].id
        ).all()
        assert result.imported_count == 3
        assert len(executions) == 3
        assert len({execution.external_case_key for execution in executions}) == 3


def test_missing_test_case_code_rejects_entire_report(app):
    report = inline_report('<testcase name="sample_missing_code" />')
    with app.app_context():
        version, _ = seed_version("MISSING-CODE")

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(report, version.id)

        assert captured.value.code == "testcase_matching_failed"
        assert captured.value.items[0].reason == "missing_test_case_code"
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_unknown_test_case_code_rejects_entire_report(app):
    report = inline_report(
        '<testcase name="sample_unknown"><properties>'
        '<property name="platform_test_case_code" value="TC_SAMPLE_UNKNOWN_001" />'
        "</properties></testcase>"
    )
    with app.app_context():
        version, _ = seed_version("UNKNOWN")

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(report, version.id)

        assert captured.value.items[0].reason == "test_case_not_found"
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_matching_never_uses_same_code_from_another_version(app):
    report = inline_report(
        '<testcase name="sample_cross_version"><properties>'
        '<property name="platform_test_case_code" value="TC_CROSS_VERSION_001" />'
        "</properties></testcase>"
    )
    with app.app_context():
        target_version, _ = seed_version("TARGET", codes=())
        seed_version("OTHER", codes=("TC_CROSS_VERSION_001",))

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(report, target_version.id)

        assert captured.value.items[0].reason == "test_case_not_found"


def test_multiple_matching_errors_are_returned_together(app):
    report = inline_report(
        '<testcase classname="sample.one" name="sample_missing" />'
        '<testcase classname="sample.two" name="sample_unknown"><properties>'
        '<property name="platform_test_case_code" value="TC_SAMPLE_UNKNOWN_002" />'
        "</properties></testcase>"
    )
    with app.app_context():
        version, _ = seed_version("MULTIPLE-ERRORS")

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(report, version.id)

        assert {item.reason for item in captured.value.items} == {
            "missing_test_case_code",
            "test_case_not_found",
        }
        assert all(item.external_case_key for item in captured.value.items)
        assert all(item.suite_path == ("sample-import",) for item in captured.value.items)
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_missing_target_version_is_a_validation_error(app):
    with app.app_context():
        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(fixture_report(), 999_999)

        assert captured.value.code == "version_not_found"
        assert captured.value.items == ()


def test_duplicate_report_returns_existing_run_without_new_rows(app):
    report = fixture_report()
    with app.app_context():
        version, _ = seed_version("DUPLICATE")
        first = import_report(report, version.id)
        second = import_report(report, version.id)

        assert second.status == "already_imported"
        assert second.test_run_id == first.test_run_id
        assert second.imported_count == 0
        assert second.total_count == 4
        assert AutomationTestRun.query.count() == 1
        assert ExecutionRecord.query.count() == 4


def test_concurrent_report_constraint_returns_already_imported(app, monkeypatch):
    report = fixture_report()
    with app.app_context():
        version, _ = seed_version("CONCURRENT")
        first = import_report(report, version.id)
        service = JUnitImportService()
        original_find = service._find_existing_run
        call_count = 0

        def miss_then_find(version_id, report_hash):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return original_find(version_id, report_hash)

        monkeypatch.setattr(service, "_find_existing_run", miss_then_find)
        second = service.import_report(
            parsed_report=report,
            version_id=version.id,
            runner="Demo Automation Runner",
            environment="Automation Demo Env",
            imported_at=FIXED_IMPORTED_AT,
        )

        assert second.status == "already_imported"
        assert second.test_run_id == first.test_run_id
        assert second.imported_count == 0
        assert AutomationTestRun.query.count() == 1
        assert ExecutionRecord.query.count() == 4


def test_same_report_hash_can_be_imported_to_different_versions(app):
    report = fixture_report()
    with app.app_context():
        first_version, _ = seed_version("HASH-FIRST")
        second_version, _ = seed_version("HASH-SECOND")

        first = import_report(report, first_version.id)
        second = import_report(report, second_version.id)

        assert first.status == "imported"
        assert second.status == "imported"
        assert first.test_run_id != second.test_run_id
        assert AutomationTestRun.query.count() == 2
        assert ExecutionRecord.query.count() == 8


def test_duplicate_external_case_key_rejects_entire_report(app):
    report = fixture_report()
    duplicate_case = replace(
        report.cases[1],
        external_case_key=report.cases[0].external_case_key,
    )
    duplicate_report = replace(
        report,
        cases=(report.cases[0], duplicate_case, *report.cases[2:]),
    )
    with app.app_context():
        version, _ = seed_version("DUPLICATE-KEY")

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(duplicate_report, version.id)

        assert any(
            item.reason == "duplicate_external_case_key"
            for item in captured.value.items
        )
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_database_enforces_external_case_key_unique_within_run(app):
    with app.app_context():
        version, test_cases = seed_version("DB-UNIQUE")
        run = AutomationTestRun(
            version_id=version.id,
            report_hash="f" * 64,
        )
        db.session.add(run)
        db.session.flush()
        for code in ("TC_SAMPLE_AUDIO_001", "TC_SAMPLE_AUDIO_002"):
            test_case = db.session.get(ChecklistTestCase, test_cases[code].id)
            db.session.refresh(test_case)
            execution = ExecutionRecord(
                test_run_id=run.id,
                external_case_key="junit:v1:duplicate-key",
                result="passed",
                tester="Demo Automation Runner",
            )
            execution.capture_test_case_snapshot(test_case)
            db.session.add(execution)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_database_failure_rolls_back_run_and_all_executions(app, monkeypatch):
    with app.app_context():
        version, _ = seed_version("ROLLBACK")

        def fail_flush(*_args, **_kwargs):
            raise SQLAlchemyError("sample database failure")

        monkeypatch.setattr(db.session, "flush", fail_flush)
        with pytest.raises(JUnitImportPersistenceError) as captured:
            import_report(fixture_report(), version.id)

        assert captured.value.code == "database_error"
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_test_run_times_are_derived_without_fabrication(app):
    with app.app_context():
        version, _ = seed_version("RUN-TIMES")
        result = import_report(fixture_report(), version.id)
        run = db.session.get(AutomationTestRun, result.test_run_id)

        assert run.started_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 7, 12, 1, 0, 0, tzinfo=timezone.utc
        )
        assert run.finished_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 7, 12, 1, 1, 1, 250000, tzinfo=timezone.utc
        )
        assert run.imported_at.replace(tzinfo=timezone.utc) == FIXED_IMPORTED_AT
        assert run.created_at.replace(tzinfo=timezone.utc) == FIXED_IMPORTED_AT


def test_test_run_times_are_none_without_timestamps(app):
    report = inline_report(
        '<testcase name="sample_no_run_time"><properties>'
        '<property name="platform_test_case_code" value="TC_SAMPLE_AUDIO_001" />'
        "</properties></testcase>"
    )
    with app.app_context():
        version, _ = seed_version("NO-RUN-TIMES")
        result = import_report(report, version.id)
        run = db.session.get(AutomationTestRun, result.test_run_id)

        assert run.started_at is None
        assert run.finished_at is None


def test_missing_runner_uses_stable_automation_default(app):
    with app.app_context():
        version, _ = seed_version("DEFAULT-RUNNER")
        result = import_report(fixture_report(), version.id, runner=None)
        run = db.session.get(AutomationTestRun, result.test_run_id)

        assert run.runner == "JUnit Automation"
        assert {item.tester for item in run.executions} == {"JUnit Automation"}


def test_import_result_contains_counts_warnings_and_execution_ids(app):
    report = inline_report('<testcase name="sample_warning" />')
    with app.app_context():
        version, _ = seed_version("RESULT-STRUCTURE", codes=())

        with pytest.raises(JUnitImportValidationError) as captured:
            import_report(report, version.id)

        assert captured.value.items[0].test_case_code is None
        assert captured.value.items[0].testcase_name == "sample_warning"


def test_test_case_matching_uses_one_set_query_not_one_query_per_case(app):
    with app.app_context():
        version, _ = seed_version("QUERY-COUNT")
        select_statements = []

        def count_selects(_conn, _cursor, statement, _params, _context, _many):
            normalized = statement.lower()
            if normalized.lstrip().startswith("select") and "test_case" in normalized:
                select_statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", count_selects)
        try:
            import_report(fixture_report(), version.id)
        finally:
            event.remove(db.engine, "before_cursor_execute", count_selects)

        matching_queries = [
            statement
            for statement in select_statements
            if "test_case.code in" in statement.lower()
        ]
        assert len(matching_queries) == 1
