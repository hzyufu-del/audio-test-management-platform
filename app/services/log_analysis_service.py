from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from werkzeug.utils import secure_filename


LEVEL_NAMES = ("critical", "error", "warning", "info")
DOMAIN_NAMES = ("connection", "power", "battery", "audio", "protocol")
FINDING_LEVELS = frozenset({"critical", "error", "warning"})

LEVEL_PATTERNS = {
    "critical": re.compile(r"\b(?:critical|fatal|panic)\b", re.IGNORECASE),
    "error": re.compile(
        r"\b(?:error|failed|failure|exception)\b",
        re.IGNORECASE,
    ),
    "warning": re.compile(r"\b(?:warning|warn)\b", re.IGNORECASE),
    "info": re.compile(r"\b(?:info|notice)\b", re.IGNORECASE),
}

DOMAIN_PATTERNS = {
    "connection": re.compile(
        r"\b(?:connection|connect(?:ed|ing)?|disconnect(?:ed|ing)?|"
        r"bluetooth|wifi|network|pairing)\b",
        re.IGNORECASE,
    ),
    "power": re.compile(
        r"\b(?:power|voltage|current|charging|charger)\b",
        re.IGNORECASE,
    ),
    "battery": re.compile(
        r"\b(?:battery|soc|capacity)\b",
        re.IGNORECASE,
    ),
    "audio": re.compile(
        r"\b(?:audio|speaker|microphone|playback|recording|volume|codec)\b",
        re.IGNORECASE,
    ),
    "protocol": re.compile(
        r"\b(?:protocol|a2dp|hfp|avrcp|i2s|usb|ble)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class LogAnalysisConfig:
    max_file_size_bytes: int = 2 * 1024 * 1024
    max_filename_length: int = 200
    max_lines: int = 20_000
    max_line_length: int = 8_192
    max_findings: int = 50
    max_snippet_length: int = 240


@dataclass(frozen=True)
class LogFinding:
    line_number: int
    level: str
    domains: tuple[str, ...]
    snippet: str


@dataclass(frozen=True)
class ParsedLogAnalysis:
    filename: str
    file_size_bytes: int
    sha256: str
    total_lines: int
    level_counts: Mapping[str, int]
    risk_level: str
    domain_hits: Mapping[str, int]
    findings: tuple[LogFinding, ...]
    summary_json: str


class LogAnalysisError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LogTextParser:
    def __init__(self, config: LogAnalysisConfig | None = None):
        self.config = config or LogAnalysisConfig()

    def analyze(self, filename: str, content: bytes) -> ParsedLogAnalysis:
        safe_filename = self._validate_filename(filename)
        text = self._decode_content(content)
        lines = text.splitlines()
        self._validate_lines(lines)

        level_counts = Counter()
        domain_hits = Counter()
        findings = []
        finding_count = 0

        for line_number, line in enumerate(lines, start=1):
            level = self._classify_level(line)
            domains = self._classify_domains(line)
            if level:
                level_counts[level] += 1
            for domain in domains:
                domain_hits[domain] += 1

            if level in FINDING_LEVELS:
                finding_count += 1
                if len(findings) < self.config.max_findings:
                    findings.append(
                        LogFinding(
                            line_number=line_number,
                            level=level,
                            domains=domains,
                            snippet=self._truncate(line.strip()),
                        )
                    )

        normalized_levels = {
            level: level_counts[level] for level in LEVEL_NAMES
        }
        normalized_domains = {
            domain: domain_hits[domain] for domain in DOMAIN_NAMES
        }
        risk_level = self._risk_level(normalized_levels)
        summary = {
            "schema_version": 1,
            "total_lines": len(lines),
            "levels": normalized_levels,
            "risk_level": risk_level,
            "domains": normalized_domains,
            "findings": [
                {
                    "line_number": finding.line_number,
                    "level": finding.level,
                    "domains": list(finding.domains),
                    "snippet": finding.snippet,
                }
                for finding in findings
            ],
            "findings_truncated": finding_count > len(findings),
        }

        return ParsedLogAnalysis(
            filename=safe_filename,
            file_size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            total_lines=len(lines),
            level_counts=MappingProxyType(normalized_levels),
            risk_level=risk_level,
            domain_hits=MappingProxyType(normalized_domains),
            findings=tuple(findings),
            summary_json=json.dumps(
                summary,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    def _validate_filename(self, filename: str) -> str:
        safe_filename = secure_filename(filename or "")
        suffix = safe_filename.rsplit(".", maxsplit=1)[-1].lower()
        if (
            not safe_filename
            or "." not in safe_filename
            or suffix not in {"log", "txt"}
        ):
            raise LogAnalysisError(
                "unsupported_extension",
                "Only .log and .txt files are supported.",
            )
        if len(safe_filename) > self.config.max_filename_length:
            raise LogAnalysisError(
                "filename_too_long",
                "The sanitized filename exceeds the configured length limit.",
            )
        return safe_filename

    def _decode_content(self, content: bytes) -> str:
        if not isinstance(content, bytes):
            raise LogAnalysisError(
                "invalid_input",
                "Log content must be provided as bytes.",
            )
        if not content or not content.strip():
            raise LogAnalysisError("empty_file", "The log file is empty.")
        if len(content) > self.config.max_file_size_bytes:
            raise LogAnalysisError(
                "file_too_large",
                "The log file exceeds the configured size limit.",
            )
        if self._looks_binary(content):
            raise LogAnalysisError(
                "binary_content",
                "The selected file appears to contain binary data.",
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise LogAnalysisError(
                "invalid_utf8",
                "The log file must contain valid UTF-8 text.",
            ) from exc
        if not text.strip():
            raise LogAnalysisError("empty_file", "The log file is empty.")
        return text

    @staticmethod
    def _looks_binary(content: bytes) -> bool:
        if b"\x00" in content:
            return True
        disallowed_controls = sum(
            byte < 32 and byte not in {9, 10, 13} for byte in content
        )
        return disallowed_controls / len(content) > 0.1

    def _validate_lines(self, lines: list[str]) -> None:
        if len(lines) > self.config.max_lines:
            raise LogAnalysisError(
                "too_many_lines",
                "The log file exceeds the configured line limit.",
            )
        for line_number, line in enumerate(lines, start=1):
            if len(line) > self.config.max_line_length:
                raise LogAnalysisError(
                    "line_too_long",
                    f"Log line {line_number} exceeds the configured length limit.",
                )

    @staticmethod
    def _classify_level(line: str) -> str | None:
        for level in LEVEL_NAMES:
            if LEVEL_PATTERNS[level].search(line):
                return level
        return None

    @staticmethod
    def _classify_domains(line: str) -> tuple[str, ...]:
        return tuple(
            domain
            for domain in DOMAIN_NAMES
            if DOMAIN_PATTERNS[domain].search(line)
        )

    @staticmethod
    def _risk_level(level_counts: Mapping[str, int]) -> str:
        if level_counts["critical"]:
            return "critical"
        if level_counts["error"]:
            return "high"
        if level_counts["warning"]:
            return "medium"
        return "low"

    def _truncate(self, text: str) -> str:
        if len(text) <= self.config.max_snippet_length:
            return text
        return f"{text[: self.config.max_snippet_length - 1]}…"
