from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..extensions import db
from ..models import TestCase, TestExecution, TestRun, Version, utc_now
from .junit_xml_parser import JUnitParseIssue, NormalizedTestResult, ParsedJUnitReport


SOURCE_TYPE = "junit_xml"
DEFAULT_RUNNER = "JUnit Automation"


@dataclass(frozen=True)
class JUnitImportValidationItem:
    external_case_key: str
    suite_path: tuple[str, ...]
    classname: str | None
    testcase_name: str
    test_case_code: str | None
    reason: str


@dataclass(frozen=True)
class JUnitImportResult:
    status: str
    test_run_id: int
    report_hash: str
    total_count: int
    imported_count: int
    result_counts: Mapping[str, int]
    warnings: tuple[JUnitParseIssue, ...]
    execution_ids: tuple[int, ...]


class JUnitImportValidationError(ValueError):
    def __init__(self, code, message, items=()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.items = tuple(items)


class JUnitImportPersistenceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class JUnitImportService:
    def import_report(
        self,
        parsed_report: ParsedJUnitReport,
        version_id: int,
        runner: str | None = None,
        environment: str | None = None,
        imported_at: datetime | None = None,
    ) -> JUnitImportResult:
        imported_at = imported_at or utc_now()
        effective_runner = (runner or "").strip() or DEFAULT_RUNNER
        effective_environment = (environment or "").strip() or None

        version = db.session.get(Version, version_id)
        if version is None:
            db.session.rollback()
            raise JUnitImportValidationError(
                "version_not_found",
                "The target Version does not exist.",
            )

        existing_run = self._find_existing_run(version_id, parsed_report.report_hash)
        if existing_run is not None:
            result = self._already_imported_result(existing_run, parsed_report.issues)
            db.session.rollback()
            return result

        matched_cases = self._validate_and_match(parsed_report, version_id)
        started_at, finished_at = self._derive_run_times(parsed_report)
        test_run = TestRun(
            version_id=version.id,
            source_type=SOURCE_TYPE,
            report_hash=parsed_report.report_hash,
            runner=effective_runner,
            environment=effective_environment,
            started_at=started_at,
            finished_at=finished_at,
            imported_at=imported_at,
            created_at=imported_at,
        )
        db.session.add(test_run)

        executions = []
        for parsed_case in parsed_report.cases:
            test_case = matched_cases[parsed_case.test_case_code]
            execution = self._build_execution(
                parsed_case,
                test_case,
                test_run,
                effective_runner,
                effective_environment,
                imported_at,
            )
            db.session.add(execution)
            executions.append(execution)

        try:
            db.session.flush()
            test_run_id = test_run.id
            execution_ids = tuple(execution.id for execution in executions)
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            concurrent_run = self._find_existing_run(
                version_id,
                parsed_report.report_hash,
            )
            if concurrent_run is not None:
                result = self._already_imported_result(
                    concurrent_run,
                    parsed_report.issues,
                )
                db.session.rollback()
                return result
            raise JUnitImportPersistenceError(
                "database_error",
                "JUnit report import failed because a database constraint was violated.",
            ) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise JUnitImportPersistenceError(
                "database_error",
                "JUnit report import failed and all changes were rolled back.",
            ) from exc

        return JUnitImportResult(
            status="imported",
            test_run_id=test_run_id,
            report_hash=parsed_report.report_hash,
            total_count=parsed_report.case_count,
            imported_count=len(executions),
            result_counts=self._readonly_counts(parsed_report.result_counts),
            warnings=tuple(parsed_report.issues),
            execution_ids=execution_ids,
        )

    @staticmethod
    def _find_existing_run(version_id, report_hash):
        return db.session.scalar(
            db.select(TestRun).where(
                TestRun.version_id == version_id,
                TestRun.source_type == SOURCE_TYPE,
                TestRun.report_hash == report_hash,
            )
        )

    def _validate_and_match(self, parsed_report, version_id):
        errors = []
        key_counts = Counter(case.external_case_key for case in parsed_report.cases)
        for parsed_case in parsed_report.cases:
            if key_counts[parsed_case.external_case_key] > 1:
                errors.append(
                    self._validation_item(
                        parsed_case,
                        "duplicate_external_case_key",
                    )
                )
            if not parsed_case.test_case_code:
                errors.append(
                    self._validation_item(parsed_case, "missing_test_case_code")
                )

        codes = {
            case.test_case_code
            for case in parsed_report.cases
            if case.test_case_code
        }
        matched_rows = []
        if codes:
            matched_rows = db.session.scalars(
                db.select(TestCase).where(
                    TestCase.version_id == version_id,
                    TestCase.code.in_(codes),
                )
            ).all()
        matched_cases = {test_case.code: test_case for test_case in matched_rows}

        for parsed_case in parsed_report.cases:
            if (
                parsed_case.test_case_code
                and parsed_case.test_case_code not in matched_cases
            ):
                errors.append(
                    self._validation_item(parsed_case, "test_case_not_found")
                )

        if errors:
            db.session.rollback()
            raise JUnitImportValidationError(
                "testcase_matching_failed",
                "JUnit report contains testcases that cannot be matched safely.",
                errors,
            )
        return matched_cases

    @staticmethod
    def _validation_item(parsed_case, reason):
        return JUnitImportValidationItem(
            external_case_key=parsed_case.external_case_key,
            suite_path=tuple(parsed_case.suite_path),
            classname=parsed_case.classname,
            testcase_name=parsed_case.name,
            test_case_code=parsed_case.test_case_code,
            reason=reason,
        )

    def _derive_run_times(self, parsed_report):
        timestamped_cases = [
            case for case in parsed_report.cases if case.timestamp is not None
        ]
        if not timestamped_cases:
            return None, None

        awareness = {case.timestamp.tzinfo is not None for case in timestamped_cases}
        if len(awareness) > 1:
            items = [
                self._validation_item(case, "mixed_timestamp_awareness")
                for case in timestamped_cases
            ]
            db.session.rollback()
            raise JUnitImportValidationError(
                "invalid_run_timestamps",
                "JUnit report mixes timezone-aware and naive testcase timestamps.",
                items,
            )

        started_at = min(case.timestamp for case in timestamped_cases)
        finished_candidates = [
            case.timestamp + self._duration_delta(case.duration_seconds)
            for case in timestamped_cases
            if case.duration_seconds is not None
        ]
        finished_at = max(finished_candidates) if finished_candidates else None
        return started_at, finished_at

    @staticmethod
    def _duration_delta(duration):
        microseconds = int(duration * 1_000_000)
        return timedelta(microseconds=microseconds)

    @staticmethod
    def _build_execution(
        parsed_case: NormalizedTestResult,
        test_case,
        test_run,
        runner,
        environment,
        imported_at,
    ):
        notes = "Imported from JUnit XML."
        if parsed_case.raw_result == "error":
            notes = "Imported from JUnit XML; raw_result=error."

        execution = TestExecution(
            test_run=test_run,
            result=parsed_case.result,
            actual_result=JUnitImportService._actual_result(parsed_case),
            tester=runner,
            environment=environment,
            executed_at=parsed_case.timestamp or imported_at,
            external_case_key=parsed_case.external_case_key,
            duration_seconds=parsed_case.duration_seconds,
            notes=notes,
        )
        execution.capture_test_case_snapshot(test_case)
        return execution

    @staticmethod
    def _actual_result(parsed_case):
        if parsed_case.result != "failed":
            return ""
        parts = [
            value
            for value in (
                parsed_case.failure_message,
                parsed_case.failure_details,
            )
            if value
        ]
        return "\n".join(dict.fromkeys(parts)) or "JUnit failed result."

    def _already_imported_result(self, test_run, warnings):
        executions = list(test_run.executions)
        counts = Counter(execution.result for execution in executions)
        return JUnitImportResult(
            status="already_imported",
            test_run_id=test_run.id,
            report_hash=test_run.report_hash,
            total_count=len(executions),
            imported_count=0,
            result_counts=self._readonly_counts(counts),
            warnings=tuple(warnings),
            execution_ids=tuple(execution.id for execution in executions),
        )

    @staticmethod
    def _readonly_counts(counts):
        return MappingProxyType(
            {
                "passed": counts.get("passed", 0),
                "failed": counts.get("failed", 0),
                "skipped": counts.get("skipped", 0),
            }
        )
