import importlib.util
import inspect
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError


VALID_PAYLOAD = {
    "summary": "  Sample semantic review summary.  ",
    "issues": [
        {
            "category": "requirement_uncertainty",
            "severity": "info",
            "description": " Requirement coverage cannot be confirmed. ",
            "evidence": " Only the testcase content was provided. ",
            "suggestion": " Confirm the testcase against the requirement. ",
        }
    ],
    "missing_preconditions": [" Confirm the demo device state. "],
    "ambiguous_expectations": [],
    "missing_test_scenarios": [" Add a sample boundary scenario. "],
    "rewrite_suggestions": [" Describe one observable result. "],
    "confidence": "medium",
    "limitations": [" No source requirement was provided. "],
}


def ai_module_exists():
    try:
        return importlib.util.find_spec("app.services.ai.schemas") is not None
    except ModuleNotFoundError:
        return False


def schema_types():
    from app.services.ai.schemas import (
        IssueCategory,
        IssueSeverity,
        ProjectReviewContext,
        ReviewConfidence,
        SemanticReviewResult,
        TestCaseQualityIssue,
        TestCaseReviewContext,
        TestCaseReviewResult,
        TestCaseSnapshot,
        VersionReviewContext,
    )

    return SimpleNamespace(
        IssueCategory=IssueCategory,
        IssueSeverity=IssueSeverity,
        ProjectReviewContext=ProjectReviewContext,
        ReviewConfidence=ReviewConfidence,
        SemanticReviewResult=SemanticReviewResult,
        TestCaseQualityIssue=TestCaseQualityIssue,
        TestCaseReviewContext=TestCaseReviewContext,
        TestCaseReviewResult=TestCaseReviewResult,
        TestCaseSnapshot=TestCaseSnapshot,
        VersionReviewContext=VersionReviewContext,
    )


def valid_context():
    types = schema_types()
    return types.TestCaseReviewContext(
        test_case=types.TestCaseSnapshot(
            title="Sample Bluetooth Connection Review",
            code="TC_BT_REVIEW_001",
            module="Bluetooth",
            priority="P1",
            case_type="checklist",
            precondition="Demo device is paired with the sample accessory.",
            steps="1. Open Bluetooth settings.\n2. Connect the sample accessory.",
            expected_result=(
                "1. The settings page lists the accessory.\n"
                "2. The accessory status changes to Connected."
            ),
            status="active",
        ),
        version=types.VersionReviewContext(
            name="Demo Firmware Alpha",
            code="FW_DEMO_ALPHA",
            status="testing",
        ),
        project=types.ProjectReviewContext(
            name="Demo Audio Device A",
            code="MOCK-AUDIO-01",
        ),
    )


def response_with_content(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(response=response, error=error)
        )


def provider_factory(response=None, error=None):
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        captured["client"] = FakeClient(response=response, error=error)
        return captured["client"]

    return factory, captured


def build_deepseek_provider(response=None, error=None, **overrides):
    from app.services.ai.deepseek_provider import DeepSeekProvider

    factory, captured = provider_factory(response=response, error=error)
    values = {
        "api_key": "local-test-key",
        "model": "demo-current-model",
        "base_url": "https://api.deepseek.com",
        "timeout_seconds": 20,
        "max_output_tokens": 2000,
        "client_factory": factory,
    }
    values.update(overrides)
    return DeepSeekProvider(**values), captured


def make_status_error(error_type, status_code, message):
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type(message, response=response, body={"error": "sample"})


def test_ai_schema_module_exists():
    assert ai_module_exists()


def test_semantic_review_strips_strings_and_forbids_extra_fields():
    types = schema_types()
    result = types.SemanticReviewResult.model_validate(VALID_PAYLOAD)

    assert result.summary == "Sample semantic review summary."
    assert result.issues[0].description == (
        "Requirement coverage cannot be confirmed."
    )
    assert result.limitations == ["No source requirement was provided."]

    with pytest.raises(ValidationError):
        types.SemanticReviewResult.model_validate(
            {**VALID_PAYLOAD, "untrusted_html": "<strong>unsafe</strong>"}
        )


@pytest.mark.parametrize(
    ("field_name", "count"),
    [
        ("issues", 11),
        ("missing_preconditions", 6),
        ("ambiguous_expectations", 6),
        ("missing_test_scenarios", 9),
        ("rewrite_suggestions", 9),
    ],
)
def test_semantic_review_enforces_list_limits(field_name, count):
    types = schema_types()
    payload = dict(VALID_PAYLOAD)
    if field_name == "issues":
        payload[field_name] = [VALID_PAYLOAD["issues"][0]] * count
    else:
        payload[field_name] = [f"Sample item {index}" for index in range(count)]

    with pytest.raises(ValidationError):
        types.SemanticReviewResult.model_validate(payload)


def test_semantic_review_rejects_empty_items_and_requires_limitations():
    types = schema_types()
    with pytest.raises(ValidationError):
        types.SemanticReviewResult.model_validate(
            {**VALID_PAYLOAD, "rewrite_suggestions": ["   "]}
        )
    with pytest.raises(ValidationError):
        types.SemanticReviewResult.model_validate(
            {**VALID_PAYLOAD, "limitations": []}
        )


@pytest.mark.parametrize("score", [-1, 101])
def test_review_result_rejects_score_outside_range(score):
    types = schema_types()
    semantic = types.SemanticReviewResult.model_validate(VALID_PAYLOAD)

    with pytest.raises(ValidationError):
        types.TestCaseReviewResult(
            quality_score=score,
            rule_issues=[],
            semantic_review=semantic,
            provider_name="mock",
            is_demo=True,
        )


def test_mock_provider_is_deterministic_and_validated():
    from app.services.ai.mock_provider import MockAIProvider
    from app.services.ai.provider import AIProvider

    provider = MockAIProvider()
    context = valid_context()

    first = provider.review_test_case(context)
    second = provider.review_test_case(context)

    assert isinstance(provider, AIProvider)
    assert first == second
    assert first.limitations
    assert provider.provider_name == "mock"
    assert provider.is_demo is True


def test_deepseek_provider_requires_key_and_model():
    from app.services.ai.deepseek_provider import DeepSeekProvider
    from app.services.ai.exceptions import AIConfigurationError

    with pytest.raises(AIConfigurationError, match="尚未配置"):
        DeepSeekProvider(
            api_key="",
            model="demo-current-model",
            base_url="https://api.deepseek.com",
            timeout_seconds=20,
            max_output_tokens=2000,
        )
    with pytest.raises(AIConfigurationError, match="尚未配置"):
        DeepSeekProvider(
            api_key="local-test-key",
            model="",
            base_url="https://api.deepseek.com",
            timeout_seconds=20,
            max_output_tokens=2000,
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "http://api.deepseek.com",
        "file:///tmp/sample",
        "https://user:password@api.deepseek.com",
        "https://api.deepseek.com?token=sample",
    ],
)
def test_deepseek_provider_rejects_invalid_base_url(base_url):
    from app.services.ai.exceptions import AIConfigurationError

    with pytest.raises(AIConfigurationError, match="Base URL"):
        build_deepseek_provider(base_url=base_url)


def test_deepseek_provider_configures_client_and_request_safely():
    provider, captured = build_deepseek_provider(
        response=response_with_content(json.dumps(VALID_PAYLOAD))
    )

    result = provider.review_test_case(valid_context())
    call = captured["client"].chat.completions.calls[0]

    assert captured["api_key"] == "local-test-key"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["timeout"] == 20
    assert captured["max_retries"] == 1
    assert call["model"] == "demo-current-model"
    assert call["response_format"] == {"type": "json_object"}
    assert call["max_tokens"] == 2000
    assert call["stream"] is False
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in call
    assert [message["role"] for message in call["messages"]] == [
        "system",
        "user",
    ]
    assert "DEEPSEEK_API_KEY" not in call["messages"][1]["content"]
    assert result.summary == "Sample semantic review summary."


def test_deepseek_provider_can_enable_thinking_explicitly():
    from app.services.ai.deepseek_provider import DeepSeekProvider

    assert "thinking_enabled" in inspect.signature(
        DeepSeekProvider
    ).parameters
    provider, captured = build_deepseek_provider(
        response=response_with_content(json.dumps(VALID_PAYLOAD)),
        thinking_enabled=True,
    )

    provider.review_test_case(valid_context())

    call = captured["client"].chat.completions.calls[0]
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "reasoning_effort" not in call


def test_system_prompt_treats_testcase_commands_as_untrusted_data():
    from app.services.ai.prompts import SYSTEM_PROMPT

    lowered = SYSTEM_PROMPT.lower()
    assert "testcase" in lowered
    assert "ignore" in lowered
    assert "system prompt" in lowered
    assert "json" in lowered
    assert "requirement_uncertainty" in lowered
    assert "limitations" in lowered


def test_system_prompt_defines_the_exact_semantic_review_schema():
    from app.services.ai.prompts import SYSTEM_PROMPT

    for field_name in (
        '"category"',
        '"severity"',
        '"description"',
        '"evidence"',
        '"suggestion"',
    ):
        assert field_name in SYSTEM_PROMPT

    for enum_value in (
        "title_mismatch",
        "missing_precondition",
        "prompt_injection",
        "requirement_uncertainty",
        "other",
        '"info"',
        '"warning"',
        '"critical"',
        '"low"',
        '"medium"',
        '"high"',
    ):
        assert enum_value in SYSTEM_PROMPT


@pytest.mark.parametrize("opening", ["```json", "```"])
def test_deepseek_provider_accepts_only_complete_markdown_json_wrapper(opening):
    content = f"{opening}\n{json.dumps(VALID_PAYLOAD)}\n```"
    provider, _ = build_deepseek_provider(
        response=response_with_content(content)
    )

    result = provider.review_test_case(valid_context())

    assert result.confidence.value == "medium"


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "prefix " + json.dumps(VALID_PAYLOAD),
        "```json\n" + json.dumps(VALID_PAYLOAD),
    ],
)
def test_deepseek_provider_rejects_malformed_or_embedded_json(content):
    from app.services.ai.exceptions import AIResponseError

    provider, _ = build_deepseek_provider(
        response=response_with_content(content)
    )

    with pytest.raises(AIResponseError, match="结构校验"):
        provider.review_test_case(valid_context())


def test_deepseek_provider_rejects_schema_mismatch_and_extra_fields():
    from app.services.ai.exceptions import AIResponseError

    for payload in (
        {"summary": "Incomplete"},
        {**VALID_PAYLOAD, "quality_score": 100},
    ):
        provider, _ = build_deepseek_provider(
            response=response_with_content(json.dumps(payload))
        )
        with pytest.raises(AIResponseError, match="结构校验"):
            provider.review_test_case(valid_context())


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (SimpleNamespace(choices=[]), "空内容"),
        (SimpleNamespace(choices=[SimpleNamespace(message=None)]), "空内容"),
        (response_with_content("   "), "空内容"),
    ],
)
def test_deepseek_provider_rejects_empty_response_parts(response, message):
    from app.services.ai.exceptions import AIResponseError

    provider, _ = build_deepseek_provider(response=response)

    with pytest.raises(AIResponseError, match=message):
        provider.review_test_case(valid_context())


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            APITimeoutError(
                httpx.Request(
                    "POST",
                    "https://api.deepseek.com/chat/completions",
                )
            ),
            "请求超时",
        ),
        (
            make_status_error(
                AuthenticationError,
                401,
                "authentication failed for local-test-key",
            ),
            "尚未配置",
        ),
        (
            make_status_error(RateLimitError, 429, "rate limited"),
            "稍后重试",
        ),
        (
            APIConnectionError(
                request=httpx.Request(
                    "POST",
                    "https://api.deepseek.com/chat/completions",
                )
            ),
            "暂时不可用",
        ),
        (
            make_status_error(APIStatusError, 500, "upstream details"),
            "暂时不可用",
        ),
        (RuntimeError("sdk failed with local-test-key"), "暂时不可用"),
    ],
)
def test_deepseek_provider_maps_sdk_errors_without_leaking_key(error, message):
    from app.services.ai.exceptions import AIReviewError

    provider, _ = build_deepseek_provider(error=error)

    with pytest.raises(AIReviewError, match=message) as captured:
        provider.review_test_case(valid_context())

    assert "local-test-key" not in str(captured.value)
