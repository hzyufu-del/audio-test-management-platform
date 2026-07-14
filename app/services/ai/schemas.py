from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


PlainText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]
SummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
ProviderName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
ContextText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=12000),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IssueCategory(str, Enum):
    TITLE_MISMATCH = "title_mismatch"
    MISSING_PRECONDITION = "missing_precondition"
    UNCLEAR_STEP = "unclear_step"
    DUPLICATE_STEP = "duplicate_step"
    UNVERIFIABLE_EXPECTATION = "unverifiable_expectation"
    STEP_EXPECTATION_MISMATCH = "step_expectation_mismatch"
    MISSING_NORMAL_SCENARIO = "missing_normal_scenario"
    MISSING_EXCEPTION_SCENARIO = "missing_exception_scenario"
    MISSING_BOUNDARY_SCENARIO = "missing_boundary_scenario"
    MISSING_ENVIRONMENT = "missing_environment"
    PROMPT_INJECTION = "prompt_injection"
    REQUIREMENT_UNCERTAINTY = "requirement_uncertainty"
    OTHER = "other"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReviewConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TestCaseQualityIssue(StrictModel):
    category: IssueCategory
    severity: IssueSeverity
    description: PlainText
    evidence: PlainText
    suggestion: PlainText


class SemanticReviewResult(StrictModel):
    summary: SummaryText
    issues: Annotated[list[TestCaseQualityIssue], Field(max_length=10)]
    missing_preconditions: Annotated[list[PlainText], Field(max_length=5)]
    ambiguous_expectations: Annotated[list[PlainText], Field(max_length=5)]
    missing_test_scenarios: Annotated[list[PlainText], Field(max_length=8)]
    rewrite_suggestions: Annotated[list[PlainText], Field(max_length=8)]
    confidence: ReviewConfidence
    limitations: Annotated[list[PlainText], Field(min_length=1, max_length=8)]


class TestCaseReviewResult(StrictModel):
    quality_score: Annotated[int, Field(ge=0, le=100)]
    rule_issues: Annotated[list[TestCaseQualityIssue], Field(max_length=20)]
    semantic_review: SemanticReviewResult
    provider_name: ProviderName
    is_demo: bool


class TestCaseSnapshot(StrictModel):
    title: ContextText
    code: ContextText
    module: ContextText
    priority: ContextText
    case_type: ContextText
    precondition: ContextText
    steps: ContextText
    expected_result: ContextText
    status: ContextText


class VersionReviewContext(StrictModel):
    name: ContextText
    code: ContextText
    status: ContextText


class ProjectReviewContext(StrictModel):
    name: ContextText
    code: ContextText


class TestCaseReviewContext(StrictModel):
    test_case: TestCaseSnapshot
    version: VersionReviewContext
    project: ProjectReviewContext
