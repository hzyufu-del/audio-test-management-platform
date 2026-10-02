"""Bounded validation categories only; never retain values or error messages."""

import re
from contextlib import suppress


MAX_ENTRIES = 20
MAX_ERROR_COUNT = 10000
STAGES = frozenset({
    "api", "output_limit", "response_content", "json_parse", "schema",
    "output_safety", "business_persistence", "unknown",
})
ERROR_CATEGORIES = frozenset({
    "invalid_json", "missing_field", "extra_field", "invalid_enum",
    "invalid_type", "string_length", "collection_length", "string_pattern",
    "api_timeout", "api_authentication", "api_rate_limit", "api_unavailable",
    "output_limit", "no_usable_content", "missing_demo_scope",
    "sensitive_content", "persistence_failure", "other",
})
SCHEMA_CODES = {
    "json_invalid": "invalid_json", "missing": "missing_field",
    "extra_forbidden": "extra_field", "enum": "invalid_enum",
    "string_type": "invalid_type", "list_type": "invalid_type",
    "model_type": "invalid_type", "model_attributes_type": "invalid_type",
    "dict_type": "invalid_type", "string_too_short": "string_length",
    "string_too_long": "string_length", "too_short": "collection_length",
    "too_long": "collection_length", "string_pattern_mismatch": "string_pattern",
    "other": "other",
}
FIELD_NAMES = frozenset({
    "summary", "test_points", "case_drafts", "limitations", "category", "title",
    "description", "priority", "suggested_code", "module", "case_type",
    "precondition", "steps", "expected_result", "scenario_type", "extra_field",
})
_FIELD = "(?:" + "|".join(sorted(FIELD_NAMES)) + ")"
_SEGMENT = _FIELD + r"(?:\[(?:0|[1-9][0-9]{0,3})\])?"
_PATH = re.compile(r"(?:root|" + _SEGMENT + r"(?:\." + _SEGMENT + r"){0,4})\Z")


def _unique(values):
    return list(dict.fromkeys(values))[:MAX_ENTRIES]


def _field_path(location):
    if not isinstance(location, (tuple, list)) or not location:
        return "root"
    parts = []
    for part in location[:5]:
        if type(part) is int:
            if not 0 <= part <= 9999:
                return "extra_field"
            if not parts:
                parts.append("extra_field")
            parts[-1] += f"[{part}]"
        else:
            parts.append(part if type(part) is str and part in FIELD_NAMES else "extra_field")
    path = ".".join(parts)
    return path if len(path) <= 160 and _PATH.fullmatch(path) else "extra_field"


def validation_summary(stage, category):
    """A fixed reason code without matched text, exception, or user input."""
    return sanitize_validation_summary({
        "stage": stage, "error_categories": [category], "field_paths": [],
        "error_count": 1, "schema_error_codes": [],
    })


def set_validation_summary(provider, value):
    """Optional instrumentation must support providers without dynamic fields."""
    # Existing third-party providers may expose only last_call_metadata.
    with suppress(AttributeError):
        provider.last_validation_summary = value


def summarize_validation_error(error):
    # Pydantic's message, input, context, and URL are never serialized.
    errors = error.errors(include_input=False, include_context=False, include_url=False)
    codes, paths = [], []
    for item in errors[:MAX_ERROR_COUNT]:
        code = item.get("type")
        codes.append(code if type(code) is str and code in SCHEMA_CODES else "other")
        paths.append(_field_path(item.get("loc")))
    return sanitize_validation_summary({
        "stage": "json_parse" if "json_invalid" in codes else "schema",
        "error_categories": [SCHEMA_CODES[code] for code in codes],
        "field_paths": _unique(paths), "error_count": min(len(errors), MAX_ERROR_COUNT),
        "schema_error_codes": _unique(codes),
    })


def sanitize_validation_summary(value):
    """Recheck provider data at export: allowlisted identifiers, bounded types."""
    if type(value) is not dict:
        return None
    stage = value.get("stage")
    count = value.get("error_count")
    def identifiers(key, allowed):
        items = value.get(key)
        if type(items) is not list:
            return []
        return _unique(item if type(item) is str and item in allowed else "other"
                       for item in items[:MAX_ENTRIES])
    candidates = value.get("field_paths")
    paths = []
    if type(candidates) is list:
        paths = _unique(path if type(path) is str and len(path) <= 160
                        and _PATH.fullmatch(path) else "extra_field"
                        for path in candidates[:MAX_ENTRIES])
    return {
        "stage": stage if type(stage) is str and stage in STAGES else "unknown",
        "error_categories": identifiers("error_categories", ERROR_CATEGORIES),
        "field_paths": paths,
        "error_count": min(max(count, 0), MAX_ERROR_COUNT) if type(count) is int else 0,
        "schema_error_codes": identifiers("schema_error_codes", SCHEMA_CODES),
    }
