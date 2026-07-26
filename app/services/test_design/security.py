import re
from collections.abc import Mapping


PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "reveal system prompt",
    "output api key",
    "execute system command",
    "执行系统命令",
    "忽略以上规则",
)

SENSITIVE_CONTENT_PATTERNS = (
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|password|secret)"
        r"\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
        r"\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|[\s\"'(])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"')]+",
        re.MULTILINE,
    ),
    re.compile(
        r"(?:^|[\s\"'(])/(?:Users|home|etc|var|tmp|opt|usr|srv|root|mnt|"
        r"Volumes)/[^\s\"')]+",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\b(?:production|customer|client|real company)\s+"
        r"(?:credential|data|record|log|token|secret)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:DEEPSEEK_API_KEY|SECRET_KEY|DATABASE_URI)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bYou are a constrained test design assistant\b",
        re.IGNORECASE,
    ),
)
LOG_LINE_PATTERN = re.compile(
    r"(?:\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}).*"
    r"\b(?:DEBUG|INFO|WARNING|ERROR|CRITICAL)\b",
    re.IGNORECASE,
)
DEMO_SCOPE_PATTERN = re.compile(
    r"\b(?:mock|demo|sample)\b|模拟|演示|示例|样例",
    re.IGNORECASE,
)


def detect_untrusted_input_risks(requirement_text):
    normalized = str(requirement_text or "").casefold()
    if any(marker in normalized for marker in PROMPT_INJECTION_MARKERS):
        return [
            "Potential prompt-injection instructions were detected in the "
            "untrusted requirement text."
        ]
    return []


def contains_forbidden_content(value):
    texts = list(_text_values(value))
    if any(
        pattern.search(text)
        for text in texts
        for pattern in SENSITIVE_CONTENT_PATTERNS
    ):
        return True
    return any(
        LOG_LINE_PATTERN.search(line)
        for text in texts
        for line in text.splitlines()
    )


def contains_demo_scope(value):
    return any(DEMO_SCOPE_PATTERN.search(text) for text in _text_values(value))


def _text_values(value):
    if isinstance(value, str):
        yield value
        return
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _text_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _text_values(item)
