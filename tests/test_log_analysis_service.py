import hashlib
import json

import pytest

from app.services.log_analysis_service import (
    LogAnalysisConfig,
    LogAnalysisError,
    LogTextParser,
)


def test_analyzes_levels_domains_risk_and_summary_case_insensitively():
    content = "\n".join(
        (
            "2026-07-26 INFO Bluetooth connection established",
            "2026-07-26 WaRn battery voltage is low",
            "2026-07-26 ERROR audio protocol timeout",
            "2026-07-26 CRITICAL speaker power failure",
        )
    ).encode()

    result = LogTextParser().analyze("sample_audio.log", content)
    summary = json.loads(result.summary_json)

    assert result.filename == "sample_audio.log"
    assert result.file_size_bytes == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.total_lines == 4
    assert result.level_counts == {
        "critical": 1,
        "error": 1,
        "warning": 1,
        "info": 1,
    }
    assert result.risk_level == "critical"
    assert result.domain_hits == {
        "connection": 1,
        "power": 2,
        "battery": 1,
        "audio": 2,
        "protocol": 1,
    }
    assert [finding.line_number for finding in result.findings] == [2, 3, 4]
    assert summary["schema_version"] == 1
    assert summary["levels"] == dict(result.level_counts)
    assert summary["domains"] == dict(result.domain_hits)
    assert summary["risk_level"] == "critical"
    assert summary["total_lines"] == 4
    assert summary["findings"][0]["line_number"] == 2


@pytest.mark.parametrize(
    ("content", "expected_risk"),
    (
        (b"CRITICAL sample audio failure", "critical"),
        (b"ERROR sample audio failure", "high"),
        (b"WARNING sample battery state", "medium"),
        (b"INFO sample connection state", "low"),
    ),
)
def test_calculates_each_risk_level(content, expected_risk):
    result = LogTextParser().analyze("risk.log", content)

    assert result.risk_level == expected_risk


@pytest.mark.parametrize(
    ("content", "config", "expected_code"),
    (
        (b"", None, "empty_file"),
        (b"   \n\t", None, "empty_file"),
        (b"\xef\xbb\xbf", None, "empty_file"),
        ("\u3000\n".encode(), None, "empty_file"),
        (b"x" * 9, LogAnalysisConfig(max_file_size_bytes=8), "file_too_large"),
        (b"\xff\xfe\xfa", None, "invalid_utf8"),
        (b"INFO sample\x00binary", None, "binary_content"),
        (b"\x01\x02\x03\x04INFO sample", None, "binary_content"),
        (
            b"INFO one\nINFO two\nINFO three",
            LogAnalysisConfig(max_lines=2),
            "too_many_lines",
        ),
        (
            b"INFO line is too long",
            LogAnalysisConfig(max_line_length=8),
            "line_too_long",
        ),
    ),
)
def test_rejects_invalid_or_unbounded_content(content, config, expected_code):
    parser = LogTextParser(config)

    with pytest.raises(LogAnalysisError) as exc_info:
        parser.analyze("sample.log", content)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    "filename",
    (
        "sample.xml",
        "sample.log.exe",
        "sample",
        ".log",
    ),
)
def test_rejects_unsupported_or_unsafe_filenames(filename):
    with pytest.raises(LogAnalysisError) as exc_info:
        LogTextParser().analyze(filename, b"INFO sample")

    assert exc_info.value.code == "unsupported_extension"


def test_sanitizes_filename_and_accepts_utf8_bom():
    content = b"\xef\xbb\xbfINFO sample audio"

    result = LogTextParser().analyze("../../demo audio.TXT", content)

    assert result.filename == "demo_audio.TXT"
    assert result.total_lines == 1
    assert result.level_counts["info"] == 1


def test_rejects_filename_longer_than_configured_metadata_field():
    parser = LogTextParser(LogAnalysisConfig(max_filename_length=20))

    with pytest.raises(LogAnalysisError) as exc_info:
        parser.analyze("this_filename_is_too_long.log", b"INFO sample")

    assert exc_info.value.code == "filename_too_long"


def test_limits_findings_and_truncates_snippets_safely():
    parser = LogTextParser(
        LogAnalysisConfig(max_findings=2, max_snippet_length=24)
    )
    content = "\n".join(
        (
            "ERROR audio " + ("x" * 100),
            "WARNING battery sample",
            "CRITICAL protocol sample",
        )
    ).encode()

    result = parser.analyze("bounded.log", content)
    summary = json.loads(result.summary_json)

    assert len(result.findings) == 2
    assert result.findings[0].snippet.endswith("…")
    assert len(result.findings[0].snippet) == 24
    assert len(summary["findings"]) == 2
    assert summary["findings_truncated"] is True
    assert result.level_counts["critical"] == 1


def test_hash_is_stable_and_result_does_not_retain_original_content():
    content = (
        b"INFO private-token-that-must-not-be-retained\n"
        b"ERROR audio sample failure"
    )
    parser = LogTextParser()

    first = parser.analyze("sample.log", content)
    second = parser.analyze("renamed.txt", content)

    assert first.sha256 == second.sha256
    assert not hasattr(first, "raw_content")
    assert "private-token-that-must-not-be-retained" not in first.summary_json
    json.dumps(json.loads(first.summary_json))
