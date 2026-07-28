import json

import pytest
from pydantic import ValidationError


def valid_payload(**overrides):
    payload = {
        "summary": "Demo AI Design for a sample audio volume requirement.",
        "test_points": [
            {
                "category": "functional",
                "title": "Validate sample volume adjustment",
                "description": (
                    "Verify that changing the sample slider produces an "
                    "observable mock response."
                ),
                "priority": "P0",
            }
        ],
        "case_drafts": [
            {
                "suggested_code": "TC_AI_AUDIO_001",
                "title": "Validate normal sample volume adjustment",
                "module": "Audio",
                "priority": "P0",
                "case_type": "checklist",
                "scenario_type": "normal",
                "precondition": "Mock audio device is connected.",
                "steps": (
                    "1. Open the sample volume page.\n"
                    "2. Move the slider to 60 percent."
                ),
                "expected_result": (
                    "The displayed value and mock device response both show "
                    "60 percent."
                ),
            }
        ],
        "limitations": [
            "Generated from sample requirement text and requires human review."
        ],
    }
    payload.update(overrides)
    return payload


def test_test_design_result_accepts_strict_valid_payload():
    from app.services.test_design.schemas import TestDesignResult

    result = TestDesignResult.model_validate(valid_payload())

    assert result.summary.startswith("Demo AI Design")
    assert result.case_drafts[0].scenario_type.value == "normal"
    assert result.case_drafts[0].priority.value == "P0"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("summary",), " "),
        (("test_points", 0, "title"), ""),
        (("case_drafts", 0, "title"), " "),
        (("case_drafts", 0, "steps"), ""),
        (("case_drafts", 0, "expected_result"), ""),
        (("case_drafts", 0, "priority"), "P9"),
        (("case_drafts", 0, "case_type"), "automation"),
        (("case_drafts", 0, "scenario_type"), "chaos"),
        (("case_drafts", 0, "suggested_code"), "../unsafe"),
    ],
)
def test_test_design_result_rejects_invalid_fields(path, value):
    from app.services.test_design.schemas import TestDesignResult

    payload = valid_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        TestDesignResult.model_validate(payload)


def test_test_design_result_rejects_extra_and_missing_fields():
    from app.services.test_design.schemas import TestDesignResult

    extra = valid_payload()
    extra["raw_provider_response"] = "must not be stored"
    missing = valid_payload()
    missing.pop("limitations")

    with pytest.raises(ValidationError):
        TestDesignResult.model_validate(extra)
    with pytest.raises(ValidationError):
        TestDesignResult.model_validate(missing)


@pytest.mark.parametrize(
    ("field", "count"),
    [
        ("test_points", 0),
        ("test_points", 21),
        ("case_drafts", 0),
        ("case_drafts", 21),
        ("limitations", 0),
        ("limitations", 9),
    ],
)
def test_test_design_result_enforces_list_bounds(field, count):
    from app.services.test_design.schemas import TestDesignResult

    payload = valid_payload()
    seed = payload[field][0]
    payload[field] = [seed.copy() if isinstance(seed, dict) else seed] * count

    with pytest.raises(ValidationError):
        TestDesignResult.model_validate(payload)


def test_test_design_result_rejects_overlong_text_and_invalid_json():
    from app.services.test_design.schemas import TestDesignResult

    payload = valid_payload(summary="x" * 2001)
    with pytest.raises(ValidationError):
        TestDesignResult.model_validate(payload)

    with pytest.raises(ValidationError):
        TestDesignResult.model_validate_json('{"summary":')


def test_test_design_context_contains_only_bounded_untrusted_text():
    from app.services.test_design.schemas import TestDesignContext

    context = TestDesignContext(
        title="  Demo audio requirement  ",
        requirement_text="  Sample volume adjustment for a mock device.  ",
    )

    assert context.model_dump() == {
        "title": "Demo audio requirement",
        "requirement_text": "Sample volume adjustment for a mock device.",
    }
    assert "project_id" not in json.dumps(context.model_dump())


def test_draft_edit_input_rejects_unknown_internal_fields():
    from app.services.test_design.schemas import DraftEditInput

    payload = valid_payload()["case_drafts"][0]
    with pytest.raises(ValidationError):
        DraftEditInput.model_validate(
            {**payload, "accepted_test_case_id": 99}
        )
