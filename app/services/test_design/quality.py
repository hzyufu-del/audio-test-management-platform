import re

from .schemas import QualityAssessment, ScenarioType, TestDesignResult


DIMENSION_MAXIMUMS = {
    "structure_completeness": 25,
    "normal_scenario": 15,
    "negative_scenario": 15,
    "boundary_scenario": 15,
    "precondition_quality": 10,
    "executable_steps": 10,
    "observable_expected_result": 10,
}
OBSERVABLE_MARKERS = (
    "show",
    "display",
    "status",
    "value",
    "response",
    "return",
    "update",
    "connected",
    "error",
    "remain",
    "显示",
    "状态",
    "数值",
    "响应",
    "返回",
)


def score_test_design(
    result: TestDesignResult,
    *,
    risk_warnings=None,
) -> QualityAssessment:
    scenarios = {draft.scenario_type for draft in result.case_drafts}
    dimensions = {
        "structure_completeness": 25,
        "normal_scenario": (
            15 if ScenarioType.NORMAL in scenarios else 0
        ),
        "negative_scenario": (
            15 if ScenarioType.NEGATIVE in scenarios else 0
        ),
        "boundary_scenario": (
            15 if ScenarioType.BOUNDARY in scenarios else 0
        ),
        "precondition_quality": (
            10
            if all(len(draft.precondition) >= 5 for draft in result.case_drafts)
            else 0
        ),
        "executable_steps": (
            10
            if all(_has_executable_steps(draft.steps) for draft in result.case_drafts)
            else 0
        ),
        "observable_expected_result": (
            10
            if all(
                _is_observable(draft.expected_result)
                for draft in result.case_drafts
            )
            else 0
        ),
    }
    missing_scenarios = [
        scenario
        for scenario in (
            ScenarioType.NORMAL,
            ScenarioType.NEGATIVE,
            ScenarioType.BOUNDARY,
        )
        if scenario not in scenarios
    ]
    deduction_reasons = []
    for dimension, maximum in DIMENSION_MAXIMUMS.items():
        if dimensions[dimension] < maximum:
            deduction_reasons.append(
                f"{dimension.replace('_', ' ').title()} is incomplete."
            )

    return QualityAssessment(
        quality_score=max(0, min(100, sum(dimensions.values()))),
        dimension_scores=dimensions,
        missing_scenarios=missing_scenarios,
        deduction_reasons=deduction_reasons,
        risk_warnings=list(risk_warnings or []),
    )


def _has_executable_steps(value):
    numbered_lines = [
        line
        for line in str(value or "").splitlines()
        if re.match(r"^\s*\d+[.)]\s+\S+", line)
    ]
    return len(numbered_lines) >= 2


def _is_observable(value):
    normalized = str(value or "").casefold()
    return any(marker in normalized for marker in OBSERVABLE_MARKERS)
