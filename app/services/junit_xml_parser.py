from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Mapping
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException


UNNAMED_SUITE = "<unnamed-suite>"


@dataclass(frozen=True)
class ParserConfig:
    max_file_size_bytes: int = 5 * 1024 * 1024
    max_test_cases: int = 10_000
    max_suite_depth: int = 20
    max_properties_per_case: int = 50
    max_property_name_length: int = 128
    max_property_value_length: int = 1024
    max_failure_message_length: int = 1024
    max_failure_details_length: int = 8192


@dataclass(frozen=True)
class JUnitParseIssue:
    code: str
    message: str
    case_identifier: str | None = None


@dataclass(frozen=True)
class NormalizedTestResult:
    test_case_code: str | None
    name: str
    classname: str | None
    suite_path: tuple[str, ...]
    external_case_key: str
    result: str
    raw_result: str
    duration_seconds: Decimal | None
    failure_message: str | None
    failure_details: str | None
    timestamp: datetime | None
    occurrence_index: int


@dataclass(frozen=True)
class ParsedJUnitReport:
    report_hash: str
    cases: tuple[NormalizedTestResult, ...]
    issues: tuple[JUnitParseIssue, ...]
    suite_count: int
    case_count: int
    result_counts: Mapping[str, int]


class JUnitParseError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        line: int | None = None,
        column: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.column = column


class JUnitXmlParser:
    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()

    def parse(self, content: bytes) -> ParsedJUnitReport:
        if not isinstance(content, bytes):
            raise JUnitParseError(
                "invalid_input",
                "JUnit XML content must be provided as bytes.",
            )
        if len(content) > self.config.max_file_size_bytes:
            raise JUnitParseError(
                "file_too_large",
                "JUnit XML content exceeds the configured size limit.",
            )

        report_hash = hashlib.sha256(content).hexdigest()
        root = self._parse_xml(content)
        if root.tag not in {"testsuite", "testsuites"}:
            raise JUnitParseError(
                "unsupported_root",
                "JUnit XML root must be testsuite or testsuites.",
            )

        cases = []
        issues = []
        occurrences = defaultdict(int)
        suite_count = [0]

        if root.tag == "testsuite":
            self._parse_suite(
                root,
                (),
                None,
                1,
                cases,
                issues,
                occurrences,
                suite_count,
            )
        else:
            for child in root:
                if child.tag == "testsuite":
                    self._parse_suite(
                        child,
                        (),
                        None,
                        1,
                        cases,
                        issues,
                        occurrences,
                        suite_count,
                    )

        if not cases:
            raise JUnitParseError(
                "empty_report",
                "JUnit XML report does not contain any testcases.",
            )

        counts = Counter(case.result for case in cases)
        result_counts = MappingProxyType(
            {
                "passed": counts["passed"],
                "failed": counts["failed"],
                "skipped": counts["skipped"],
            }
        )
        return ParsedJUnitReport(
            report_hash=report_hash,
            cases=tuple(cases),
            issues=tuple(issues),
            suite_count=suite_count[0],
            case_count=len(cases),
            result_counts=result_counts,
        )

    @staticmethod
    def _parse_xml(content):
        try:
            return fromstring(
                content,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except DefusedXmlException as exc:
            raise JUnitParseError(
                "unsafe_xml",
                "JUnit XML contains a prohibited DTD or entity declaration.",
            ) from exc
        except ParseError as exc:
            line, column = getattr(exc, "position", (None, None))
            raise JUnitParseError(
                "malformed_xml",
                "JUnit XML is malformed.",
                line=line,
                column=column,
            ) from exc

    def _parse_suite(
        self,
        element,
        parent_path,
        inherited_timestamp,
        depth,
        cases,
        issues,
        occurrences,
        suite_count,
    ):
        if depth > self.config.max_suite_depth:
            raise JUnitParseError(
                "suite_depth_exceeded",
                "JUnit XML suite nesting exceeds the configured depth limit.",
            )

        suite_count[0] += 1
        suite_name = (element.get("name") or "").strip() or UNNAMED_SUITE
        suite_path = parent_path + (suite_name,)
        suite_identifier = " / ".join(suite_path)
        suite_timestamp = self._timestamp_or_fallback(
            element.get("timestamp"),
            inherited_timestamp,
            issues,
            suite_identifier,
        )

        for child in element:
            if child.tag == "testcase":
                if len(cases) >= self.config.max_test_cases:
                    raise JUnitParseError(
                        "too_many_testcases",
                        "JUnit XML contains more testcases than the configured limit.",
                    )
                cases.append(
                    self._parse_testcase(
                        child,
                        suite_path,
                        suite_timestamp,
                        issues,
                        occurrences,
                    )
                )
            elif child.tag == "testsuite":
                self._parse_suite(
                    child,
                    suite_path,
                    suite_timestamp,
                    depth + 1,
                    cases,
                    issues,
                    occurrences,
                    suite_count,
                )

    def _parse_testcase(
        self,
        element,
        suite_path,
        suite_timestamp,
        issues,
        occurrences,
    ):
        name = (element.get("name") or "").strip()
        if not name:
            raise JUnitParseError(
                "missing_testcase_name",
                "JUnit testcase must have a non-blank name.",
            )

        classname = (element.get("classname") or "").strip() or None
        identifier = self._case_identifier(suite_path, classname, name)
        test_case_code = self._extract_test_case_code(element, identifier, issues)
        result, raw_result, outcome = self._parse_outcome(element)
        duration = self._parse_duration(element.get("time"), identifier)
        timestamp = self._timestamp_or_fallback(
            element.get("timestamp"),
            suite_timestamp,
            issues,
            identifier,
        )
        failure_message, failure_details = self._failure_content(
            outcome,
            identifier,
            issues,
        )

        identity = (suite_path, classname or "", name)
        occurrence_index = occurrences[identity]
        occurrences[identity] += 1
        external_case_key = self._external_case_key(
            suite_path,
            classname,
            name,
            occurrence_index,
        )
        return NormalizedTestResult(
            test_case_code=test_case_code,
            name=name,
            classname=classname,
            suite_path=suite_path,
            external_case_key=external_case_key,
            result=result,
            raw_result=raw_result,
            duration_seconds=duration,
            failure_message=failure_message,
            failure_details=failure_details,
            timestamp=timestamp,
            occurrence_index=occurrence_index,
        )

    def _extract_test_case_code(self, element, identifier, issues):
        properties = []
        for child in element:
            if child.tag == "properties":
                properties.extend(
                    item for item in child if item.tag == "property"
                )

        if len(properties) > self.config.max_properties_per_case:
            raise JUnitParseError(
                "property_limit_exceeded",
                "JUnit testcase properties exceed the configured count limit.",
            )

        codes = []
        for prop in properties:
            name = prop.get("name") or ""
            value = prop.get("value")
            if value is None:
                value = prop.text or ""
            if (
                len(name) > self.config.max_property_name_length
                or len(value) > self.config.max_property_value_length
            ):
                raise JUnitParseError(
                    "property_limit_exceeded",
                    "JUnit testcase property exceeds the configured length limit.",
                )
            if name.strip() == "platform_test_case_code" and value.strip():
                codes.append(value.strip())

        distinct_codes = list(dict.fromkeys(codes))
        if len(distinct_codes) > 1:
            raise JUnitParseError(
                "ambiguous_test_case_code",
                "JUnit testcase contains conflicting platform test case codes.",
            )
        if distinct_codes:
            return distinct_codes[0]

        issues.append(
            JUnitParseIssue(
                code="missing_test_case_code",
                message="JUnit testcase does not define platform_test_case_code.",
                case_identifier=identifier,
            )
        )
        return None

    @staticmethod
    def _parse_outcome(element):
        outcomes = [
            child
            for child in element
            if child.tag in {"failure", "error", "skipped"}
        ]
        if len(outcomes) > 1:
            raise JUnitParseError(
                "conflicting_outcomes",
                "JUnit testcase contains conflicting outcome nodes.",
            )
        if not outcomes:
            return "passed", "passed", None

        outcome = outcomes[0]
        if outcome.tag == "failure":
            return "failed", "failed", outcome
        if outcome.tag == "error":
            return "failed", "error", outcome
        return "skipped", "skipped", outcome

    @staticmethod
    def _parse_duration(raw_duration, identifier):
        if raw_duration is None or not raw_duration.strip():
            return None
        try:
            duration = Decimal(raw_duration.strip())
        except InvalidOperation as exc:
            raise JUnitParseError(
                "invalid_duration",
                f"JUnit testcase duration is invalid for {identifier}.",
            ) from exc
        if not duration.is_finite() or duration < 0:
            raise JUnitParseError(
                "invalid_duration",
                f"JUnit testcase duration is invalid for {identifier}.",
            )
        return duration

    def _timestamp_or_fallback(self, raw_timestamp, fallback, issues, identifier):
        if raw_timestamp is None or not raw_timestamp.strip():
            return fallback
        try:
            timestamp = datetime.fromisoformat(
                raw_timestamp.strip().replace("Z", "+00:00")
            )
        except ValueError:
            issues.append(
                JUnitParseIssue(
                    code="invalid_timestamp",
                    message="JUnit timestamp is invalid and a safe fallback was used.",
                    case_identifier=identifier,
                )
            )
            return fallback

        # Naive timestamps remain naive; aware timestamps are normalized to UTC.
        if timestamp.tzinfo is not None:
            return timestamp.astimezone(timezone.utc)
        return timestamp

    def _failure_content(self, outcome, identifier, issues):
        if outcome is None or outcome.tag == "skipped":
            return None, None

        failure_type = (outcome.get("type") or "").strip()
        message = (outcome.get("message") or "").strip()
        if failure_type and message:
            combined_message = f"{failure_type}: {message}"
        else:
            combined_message = failure_type or message
        if not combined_message:
            combined_message = "JUnit failed result without a message."

        details = " ".join("".join(outcome.itertext()).split()) or None
        combined_message = self._truncate_with_issue(
            combined_message,
            self.config.max_failure_message_length,
            "failure_message_truncated",
            "JUnit failure message was truncated to the configured limit.",
            identifier,
            issues,
        )
        if details is not None:
            details = self._truncate_with_issue(
                details,
                self.config.max_failure_details_length,
                "failure_details_truncated",
                "JUnit failure details were truncated to the configured limit.",
                identifier,
                issues,
            )
        return combined_message, details

    @staticmethod
    def _truncate_with_issue(
        value,
        limit,
        issue_code,
        issue_message,
        identifier,
        issues,
    ):
        if len(value) <= limit:
            return value
        issues.append(
            JUnitParseIssue(
                code=issue_code,
                message=issue_message,
                case_identifier=identifier,
            )
        )
        return value[:limit]

    @staticmethod
    def _external_case_key(suite_path, classname, name, occurrence_index):
        canonical = json.dumps(
            {
                "classname": classname or "",
                "name": name,
                "occurrence_index": occurrence_index,
                "suite_path": list(suite_path),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"junit:v1:{hashlib.sha256(canonical).hexdigest()}"

    @staticmethod
    def _case_identifier(suite_path, classname, name):
        parts = [" / ".join(suite_path)]
        if classname:
            parts.append(classname)
        parts.append(name)
        return "::".join(parts)
