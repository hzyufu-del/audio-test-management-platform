import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.junit_xml_parser import (
    JUnitParseError,
    JUnitXmlParser,
    ParserConfig,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "junit"


def fixture_bytes(name):
    return (FIXTURE_DIR / name).read_bytes()


def parse(xml, config=None):
    content = xml if isinstance(xml, bytes) else xml.encode("utf-8")
    return JUnitXmlParser(config).parse(content)


def error_code(xml, config=None):
    with pytest.raises(JUnitParseError) as captured:
        parse(xml, config)
    return captured.value


def test_default_parser_config_uses_bounded_security_limits():
    config = ParserConfig()

    assert config.max_file_size_bytes == 5 * 1024 * 1024
    assert config.max_test_cases == 10_000
    assert config.max_suite_depth == 20
    assert config.max_properties_per_case == 50
    assert config.max_property_name_length == 128
    assert config.max_property_value_length == 1024
    assert config.max_failure_message_length == 1024
    assert config.max_failure_details_length == 8192


def test_testsuite_root_and_all_results_are_parsed():
    report = parse(fixture_bytes("sample_results.xml"))

    assert report.suite_count == 1
    assert report.case_count == 4
    assert report.result_counts == {"passed": 1, "failed": 2, "skipped": 1}
    assert [case.raw_result for case in report.cases] == [
        "passed",
        "failed",
        "error",
        "skipped",
    ]
    assert [case.result for case in report.cases] == [
        "passed",
        "failed",
        "failed",
        "skipped",
    ]


def test_testsuites_root_and_nested_suite_path_are_parsed():
    report = parse(fixture_bytes("nested_suites.xml"))

    assert report.suite_count == 2
    assert report.cases[0].suite_path == ("sample-outer", "sample-inner")


def test_empty_suite_name_uses_stable_placeholder():
    report = parse('<testsuite name="  "><testcase name="sample_case" /></testsuite>')

    assert report.cases[0].suite_path == ("<unnamed-suite>",)


def test_duration_is_parsed_as_decimal():
    report = parse(fixture_bytes("sample_results.xml"))

    assert report.cases[0].duration_seconds == Decimal("1.250")
    assert isinstance(report.cases[0].duration_seconds, Decimal)


@pytest.mark.parametrize("duration", ["invalid", "-1", "NaN", "Infinity"])
def test_invalid_negative_or_non_finite_duration_is_fatal(duration):
    error = error_code(
        f'<testsuite name="sample"><testcase name="sample_case" time="{duration}" /></testsuite>'
    )

    assert error.code == "invalid_duration"


def test_testcase_timestamp_is_normalized_to_utc():
    report = parse(fixture_bytes("sample_results.xml"))

    assert report.cases[0].timestamp == datetime(
        2026,
        7,
        12,
        1,
        1,
        tzinfo=timezone.utc,
    )


def test_nearest_suite_timestamp_is_used_as_fallback():
    report = parse(fixture_bytes("nested_suites.xml"))

    assert report.cases[0].timestamp == datetime(
        2026,
        7,
        12,
        2,
        0,
        tzinfo=timezone.utc,
    )


def test_naive_timestamp_remains_naive():
    report = parse(
        '<testsuite name="sample"><testcase name="sample_case" timestamp="2026-07-12T03:00:00" /></testsuite>'
    )

    assert report.cases[0].timestamp == datetime(2026, 7, 12, 3, 0, 0)
    assert report.cases[0].timestamp.tzinfo is None


def test_missing_timestamp_returns_none():
    report = parse('<testsuite name="sample"><testcase name="sample_case" /></testsuite>')

    assert report.cases[0].timestamp is None


def test_invalid_testcase_timestamp_warns_and_falls_back_to_suite():
    report = parse(
        '<testsuite name="sample" timestamp="2026-07-12T04:00:00Z">'
        '<testcase name="sample_case" timestamp="not-a-time" />'
        "</testsuite>"
    )

    assert report.cases[0].timestamp == datetime(
        2026,
        7,
        12,
        4,
        0,
        tzinfo=timezone.utc,
    )
    assert any(issue.code == "invalid_timestamp" for issue in report.issues)


def test_failure_and_error_messages_include_type_and_safe_details():
    report = parse(fixture_bytes("sample_results.xml"))
    failure = report.cases[1]
    error = report.cases[2]

    assert failure.failure_message == "AssertionError: Sample connection state mismatch"
    assert failure.failure_details == "Sample expected state did not match demo output."
    assert error.failure_message == "RuntimeError: Sample recovery setup error"
    assert error.failure_details == "Demo setup could not continue."


def test_platform_test_case_code_is_extracted():
    report = parse(fixture_bytes("sample_results.xml"))

    assert report.cases[0].test_case_code == "TC_SAMPLE_AUDIO_001"


def test_missing_or_blank_test_case_code_adds_warning():
    report = parse(
        '<testsuite name="sample"><testcase name="sample_case">'
        '<properties><property name="platform_test_case_code" value="  " /></properties>'
        "</testcase></testsuite>"
    )

    assert report.cases[0].test_case_code is None
    assert [issue.code for issue in report.issues] == ["missing_test_case_code"]


def test_parameterized_name_is_preserved():
    report = parse(fixture_bytes("parameterized_duplicates.xml"))

    assert report.cases[0].name == "test_codec[aac]"
    assert report.cases[2].name == "test_codec[sbc]"


def test_duplicate_cases_receive_incrementing_occurrence_and_unique_keys():
    report = parse(fixture_bytes("parameterized_duplicates.xml"))

    assert [case.occurrence_index for case in report.cases] == [0, 1, 0]
    assert len({case.external_case_key for case in report.cases}) == 3


def test_external_case_keys_are_stable_across_repeated_parsing():
    content = fixture_bytes("parameterized_duplicates.xml")

    first = parse(content)
    second = parse(content)

    assert [case.external_case_key for case in first.cases] == [
        case.external_case_key for case in second.cases
    ]
    assert all(case.external_case_key.startswith("junit:v1:") for case in first.cases)


def test_same_case_identity_in_different_suites_has_different_keys():
    report = parse(
        "<testsuites>"
        '<testsuite name="sample-a"><testcase classname="sample.case" name="test_equal" /></testsuite>'
        '<testsuite name="sample-b"><testcase classname="sample.case" name="test_equal" /></testsuite>'
        "</testsuites>"
    )

    assert report.cases[0].external_case_key != report.cases[1].external_case_key


def test_report_hash_uses_original_xml_bytes():
    content = fixture_bytes("sample_results.xml")
    report = parse(content)

    assert report.report_hash == hashlib.sha256(content).hexdigest()


def test_malformed_xml_returns_safe_error_location_without_xml_echo():
    content = b'<testsuite name="sample"><testcase name="sample_case"></testsuite>'
    error = error_code(content)

    assert error.code == "malformed_xml"
    assert error.line is not None
    assert error.column is not None
    assert "<testsuite" not in str(error)


def test_unsupported_root_is_rejected():
    error = error_code("<sample-report />")

    assert error.code == "unsupported_root"


def test_report_without_testcases_is_rejected():
    error = error_code('<testsuite name="sample" />')

    assert error.code == "empty_report"


@pytest.mark.parametrize("name_attribute", ["", 'name=""', 'name="   "'])
def test_testcase_requires_non_blank_name(name_attribute):
    error = error_code(
        f'<testsuite name="sample"><testcase {name_attribute} /></testsuite>'
    )

    assert error.code == "missing_testcase_name"


def test_conflicting_outcome_nodes_are_rejected():
    error = error_code(
        '<testsuite name="sample"><testcase name="sample_case">'
        '<failure message="Sample failure" /><skipped message="Sample skip" />'
        "</testcase></testsuite>"
    )

    assert error.code == "conflicting_outcomes"


@pytest.mark.parametrize(
    "unsafe_xml",
    [
        b'<!DOCTYPE testsuite [<!ENTITY sample "demo">]><testsuite name="sample"><testcase name="&sample;" /></testsuite>',
        b'<!DOCTYPE testsuite SYSTEM "file:///sample/demo.dtd"><testsuite name="sample" />',
    ],
)
def test_dtd_and_entities_are_rejected(unsafe_xml):
    error = error_code(unsafe_xml)

    assert error.code == "unsafe_xml"
    assert "DOCTYPE" not in str(error)


def test_file_size_limit_is_checked_before_parsing():
    config = ParserConfig(max_file_size_bytes=20)
    error = error_code(b"<testsuite name='sample' />", config)

    assert error.code == "file_too_large"


def test_testcase_count_limit_is_enforced():
    config = ParserConfig(max_test_cases=1)
    error = error_code(
        '<testsuite name="sample"><testcase name="sample_one" />'
        '<testcase name="sample_two" /></testsuite>',
        config,
    )

    assert error.code == "too_many_testcases"


def test_suite_depth_limit_is_enforced():
    config = ParserConfig(max_suite_depth=2)
    error = error_code(
        '<testsuites><testsuite name="one"><testsuite name="two">'
        '<testsuite name="three"><testcase name="sample_case" />'
        "</testsuite></testsuite></testsuite></testsuites>",
        config,
    )

    assert error.code == "suite_depth_exceeded"


def test_failure_text_is_truncated_with_warnings():
    config = ParserConfig(
        max_failure_message_length=12,
        max_failure_details_length=14,
    )
    report = parse(
        '<testsuite name="sample"><testcase name="sample_case">'
        '<failure type="SampleError" message="A sample message that is long">'
        "Sample failure details that are intentionally long."
        "</failure></testcase></testsuite>",
        config,
    )

    assert len(report.cases[0].failure_message) == 12
    assert len(report.cases[0].failure_details) == 14
    assert {issue.code for issue in report.issues} == {
        "failure_message_truncated",
        "failure_details_truncated",
        "missing_test_case_code",
    }


@pytest.mark.parametrize(
    ("properties", "config"),
    [
        (
            '<property name="sample_one" value="demo" />'
            '<property name="sample_two" value="demo" />',
            ParserConfig(max_properties_per_case=1),
        ),
        (
            '<property name="property_name_too_long" value="demo" />',
            ParserConfig(max_property_name_length=8),
        ),
        (
            '<property name="sample" value="property value too long" />',
            ParserConfig(max_property_value_length=8),
        ),
    ],
)
def test_property_count_and_length_limits_are_enforced(properties, config):
    error = error_code(
        '<testsuite name="sample"><testcase name="sample_case"><properties>'
        f"{properties}</properties></testcase></testsuite>",
        config,
    )

    assert error.code == "property_limit_exceeded"


def test_system_output_is_not_returned_or_stored():
    report = parse(
        '<testsuite name="sample"><testcase name="sample_case">'
        "<system-out>Sample output that must be ignored.</system-out>"
        "<system-err>Sample error output that must be ignored.</system-err>"
        "</testcase></testsuite>"
    )

    assert report.cases[0].failure_details is None
    assert "Sample output" not in repr(report)


def test_parser_rejects_non_bytes_input():
    with pytest.raises(JUnitParseError) as captured:
        JUnitXmlParser().parse("<testsuite />")

    assert captured.value.code == "invalid_input"


def test_parser_does_not_require_flask_application_context():
    report = parse(fixture_bytes("sample_results.xml"))

    assert report.case_count == 4
