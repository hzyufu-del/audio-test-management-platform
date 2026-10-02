import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from types import SimpleNamespace

import pytest

from app.services.ai.exceptions import AIProviderError, AIResponseError
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design.schemas import TestDesignContext as DesignContext


MISSING = object()


@pytest.fixture()
def context():
    return DesignContext(
        title="Demo 音量调节",
        requirement_text="Sample audio volume adjustment for a mock connected device.",
    )


def canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def payload():
    return {
        "summary": "Demo AI Design for a sample audio requirement.",
        "test_points": [
            {
                "category": "functional",
                "title": "Validate sample audio behavior",
                "description": "Verify one observable mock audio response.",
                "priority": "P0",
            }
        ],
        "case_drafts": [
            {
                "suggested_code": "TC_AI_AUDIO_001",
                "title": "Validate sample audio behavior",
                "module": "Audio",
                "priority": "P0",
                "case_type": "checklist",
                "scenario_type": "normal",
                "precondition": "Mock audio device is connected.",
                "steps": "1. Open the sample page.\n2. Trigger the action.",
                "expected_result": "The mock status shows the expected value.",
            }
        ],
        "limitations": ["Requires human review."],
    }


def response(content, *, model=MISSING, usage=MISSING, finish_reason=MISSING):
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    if finish_reason is not MISSING:
        choice.finish_reason = finish_reason
    result = SimpleNamespace(choices=[choice])
    if model is not MISSING:
        result.model = model
    if usage is not MISSING:
        result.usage = usage
    return result


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_provider(*outcomes, **overrides):
    from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider

    captured = {}

    def client_factory(**kwargs):
        captured.update(kwargs)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions(outcomes))
        )
        captured["client"] = client
        return client

    values = {
        "api_key": "sample-key",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "timeout_seconds": 7,
        "max_output_tokens": 1200,
        "client_factory": client_factory,
    }
    values.update(overrides)
    return DeepSeekTestDesignProvider(**values), captured


def metadata_class():
    from app.services.test_design import provider

    result = getattr(provider, "GenerationMetadata", None)
    assert result is not None, "Provider contract must expose GenerationMetadata"
    return result


def prompt_functions():
    from app.services.test_design import prompts

    assert callable(getattr(prompts, "build_test_design_messages", None))
    assert callable(getattr(prompts, "prompt_hash", None))
    assert callable(getattr(prompts, "requirement_hash", None))
    return prompts


def test_generation_metadata_is_frozen_and_has_only_optional_evidence_fields():
    metadata = metadata_class()()

    assert asdict(metadata) == dict.fromkeys(
        (
            "provider_model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "finish_reason",
            "temperature",
            "max_tokens",
            "input_chars",
            "output_chars",
        )
    )
    with pytest.raises(FrozenInstanceError):
        metadata.total_tokens = 12
    assert getattr(MockTestDesignProvider(), "last_call_metadata", MISSING) is None


@pytest.mark.parametrize(
    "field",
    [
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "max_tokens",
        "input_chars",
        "output_chars",
    ],
)
@pytest.mark.parametrize("invalid", [True, False, -1, 1.2, "12", {}, []])
def test_metadata_rejects_non_integer_or_negative_counter_values(field, invalid):
    metadata = metadata_class()(**{field: invalid})

    assert getattr(metadata, field) is None


def test_metadata_preserves_zero_counters_and_bounded_optional_strings():
    metadata = metadata_class()(
        provider_model="deepseek-chat-v2",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        finish_reason="stop",
        temperature=0,
        max_tokens=0,
        input_chars=0,
        output_chars=0,
    )

    assert metadata.provider_model == "deepseek-chat-v2"
    assert metadata.finish_reason == "stop"
    assert metadata.temperature == 0
    assert metadata.total_tokens == 0


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("provider_model", ""),
        ("provider_model", "   "),
        ("provider_model", "x" * 121),
        ("provider_model", 123),
        ("finish_reason", ""),
        ("finish_reason", "x" * 41),
        ("finish_reason", {"private": "upstream"}),
        ("temperature", True),
        ("temperature", -1),
        ("temperature", "0.7"),
        ("temperature", float("nan")),
        ("temperature", float("inf")),
    ],
)
def test_metadata_discards_invalid_optional_strings_or_temperature(field, invalid):
    assert getattr(metadata_class()(**{field: invalid}), field) is None


def test_message_builder_sends_canonical_validated_context_without_mutable_state(context):
    prompts = prompt_functions()
    messages = prompts.build_test_design_messages(context)

    assert messages == [
        {"role": "system", "content": prompts.TEST_DESIGN_SYSTEM_PROMPT},
        {"role": "user", "content": canonical_json(context.model_dump(mode="json"))},
    ]
    messages[0]["content"] = "tampered"
    assert prompts.build_test_design_messages(context)[0]["content"] == (
        prompts.TEST_DESIGN_SYSTEM_PROMPT
    )


def test_hashes_use_utf8_and_prompt_hash_is_stable_for_static_template(context):
    prompts = prompt_functions()

    assert prompts.requirement_hash(context.requirement_text) == hashlib.sha256(
        context.requirement_text.encode("utf-8")
    ).hexdigest()
    assert prompts.requirement_hash("模拟需求文本") == hashlib.sha256(
        "模拟需求文本".encode("utf-8")
    ).hexdigest()
    first = prompts.prompt_hash()
    assert first == prompts.prompt_hash()
    assert len(first) == 64
    assert all(character in "0123456789abcdef" for character in first)
    prompts.build_test_design_messages(
        DesignContext(
            title="Other mock request",
            requirement_text="Sample Bluetooth connection requirement for a mock device.",
        )
    )
    assert prompts.prompt_hash() == first


def test_prompt_hash_changes_with_the_actual_sent_system_prompt(monkeypatch, context):
    prompts = prompt_functions()
    before = prompts.prompt_hash()
    changed = prompts.TEST_DESIGN_SYSTEM_PROMPT + "\nInclude sample edge cases."
    monkeypatch.setattr(prompts, "TEST_DESIGN_SYSTEM_PROMPT", changed)
    provider, captured = make_provider(response(canonical_json(payload())))

    provider.generate(context)

    assert prompts.prompt_hash() != before
    assert captured["client"].chat.completions.calls[0]["messages"][0]["content"] == changed


def test_deepseek_records_actual_response_metadata_and_exact_sent_lengths(context):
    raw_content = " \n" + canonical_json(payload()) + "\n "
    provider, captured = make_provider(
        response(
            raw_content,
            model="deepseek-chat-actual",
            usage=SimpleNamespace(prompt_tokens=34, completion_tokens=51, total_tokens=85),
            finish_reason="stop",
        )
    )

    result = provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    assert result.summary.startswith("Demo AI Design")
    assert metadata.provider_model == "deepseek-chat-actual"
    assert metadata.prompt_tokens == 34
    assert metadata.completion_tokens == 51
    assert metadata.total_tokens == 85
    assert metadata.finish_reason == "stop"
    assert metadata.temperature is None
    assert metadata.max_tokens == 1200
    assert metadata.output_chars == len(raw_content)
    call = captured["client"].chat.completions.calls[0]
    assert metadata.input_chars == sum(len(item["content"]) for item in call["messages"])
    assert call["messages"] == prompt_functions().build_test_design_messages(context)
    assert "temperature" not in call
    assert provider.provider_model == "deepseek-chat"


def test_deepseek_disables_implicit_sdk_retries(context):
    provider, captured = make_provider(response(canonical_json(payload())))

    provider.generate(context)

    assert captured["max_retries"] == 0
    assert len(captured["client"].chat.completions.calls) == 1


def test_prompt_json_example_obeys_the_same_strict_schema(context):
    from app.services.test_design.schemas import TestDesignResult

    prompts = prompt_functions()
    example = getattr(prompts, "TEST_DESIGN_JSON_EXAMPLE", None)
    assert isinstance(example, dict), "The JSON contract needs a complete example"
    TestDesignResult.model_validate(example)
    sent = prompts.build_test_design_messages(context)[0]["content"]
    assert canonical_json(example) in sent
    assert set(item["scenario_type"] for item in example["case_drafts"]) >= {
        "normal", "negative", "boundary",
    }


def test_length_response_is_rejected_even_if_json_matches_schema(context):
    provider, captured = make_provider(response(
        canonical_json(payload()), model="deepseek-response-model",
        usage=SimpleNamespace(prompt_tokens=30, completion_tokens=1200, total_tokens=1230),
        finish_reason="length",
    ))

    with pytest.raises(AIResponseError):
        provider.generate(context)

    assert len(captured["client"].chat.completions.calls) == 1
    assert provider.last_call_metadata.finish_reason == "length"
    assert provider.last_call_metadata.completion_tokens == 1200


def test_missing_usage_model_or_finish_reason_remains_none(context):
    provider, _captured = make_provider(response(canonical_json(payload())))

    provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    assert metadata.provider_model is None
    assert metadata.prompt_tokens is None
    assert metadata.completion_tokens is None
    assert metadata.total_tokens is None
    assert metadata.finish_reason is None
    assert metadata.temperature is None
    assert metadata.output_chars > 0


@pytest.mark.parametrize("usage", [None, False, 17, "private usage", {}, []])
def test_malformed_usage_does_not_raise_or_invent_token_counts(context, usage):
    provider, _captured = make_provider(response(canonical_json(payload()), usage=usage))

    provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    assert metadata.prompt_tokens is None
    assert metadata.completion_tokens is None
    assert metadata.total_tokens is None


def test_invalid_usage_members_are_ignored_individually(context):
    provider, _captured = make_provider(
        response(
            canonical_json(payload()),
            model={"private": "model"},
            usage=SimpleNamespace(prompt_tokens=True, completion_tokens=-1, total_tokens=12.5),
            finish_reason=["private upstream reason"],
        )
    )

    provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    assert metadata.provider_model is None
    assert metadata.finish_reason is None
    assert metadata.prompt_tokens is None
    assert metadata.completion_tokens is None
    assert metadata.total_tokens is None


def test_metadata_ignores_unrelated_raw_response_and_headers(context):
    upstream = response(
        canonical_json(payload()),
        usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )
    upstream.headers = {"Authorization": "Bearer sample-key"}
    upstream.raw_response = "private raw upstream response"
    provider, _captured = make_provider(upstream)

    provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    serialized = canonical_json(asdict(metadata))
    assert "sample-key" not in serialized
    assert "Authorization" not in serialized
    assert "private raw upstream response" not in serialized
    assert metadata.total_tokens == 0


@pytest.mark.parametrize("content", ["not valid json", "", " \n ", None])
def test_response_metadata_is_available_before_content_validation(context, content):
    provider, _captured = make_provider(
        response(
            content,
            model="deepseek-chat-actual",
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=13, total_tokens=21),
            finish_reason="length",
        )
    )

    with pytest.raises(AIResponseError):
        provider.generate(context)
    metadata = getattr(provider, "last_call_metadata", None)

    assert metadata is not None
    assert metadata.total_tokens == 21
    assert metadata.provider_model == "deepseek-chat-actual"
    assert metadata.finish_reason == "length"
    assert metadata.output_chars == (len(content) if isinstance(content, str) else None)
    assert "not valid json" not in canonical_json(asdict(metadata))


def test_each_call_resets_previous_response_metadata_even_when_sdk_raises(context):
    provider, _captured = make_provider(
        response(
            canonical_json(payload()),
            model="first-response-model",
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=13, total_tokens=21),
            finish_reason="stop",
        ),
        RuntimeError("Authorization: Bearer sample-key private SDK message"),
    )
    provider.generate(context)
    first = getattr(provider, "last_call_metadata", None)
    assert first is not None

    with pytest.raises(AIProviderError) as error:
        provider.generate(context)
    second = provider.last_call_metadata

    assert second is not first
    assert second.provider_model is None
    assert second.prompt_tokens is None
    assert second.completion_tokens is None
    assert second.total_tokens is None
    assert second.finish_reason is None
    assert second.output_chars is None
    assert second.input_chars == first.input_chars
    assert second.max_tokens == 1200
    assert "sample-key" not in str(error.value)
    assert "private SDK message" not in str(error.value)


def test_mock_records_traceable_input_and_deterministic_output_without_invented_usage(context):
    provider = MockTestDesignProvider()

    first_result = provider.generate(context)
    first = getattr(provider, "last_call_metadata", None)
    assert first is not None
    second_result = provider.generate(context)
    second = provider.last_call_metadata

    assert first is not second
    assert first == second
    assert first_result == second_result
    assert first.input_chars == sum(
        len(item["content"]) for item in prompt_functions().build_test_design_messages(context)
    )
    assert first.output_chars == len(canonical_json(first_result.model_dump(mode="json")))
    assert first.provider_model is None
    assert first.prompt_tokens is None
    assert first.completion_tokens is None
    assert first.total_tokens is None
    assert first.finish_reason is None
    assert first.temperature is None
    assert first.max_tokens is None
