from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
PlainText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]
SummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
RequirementText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2000),
]
OptionalLongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=4000),
]
RequiredLongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]
SuggestedCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=80,
        to_upper=True,
        pattern=r"^[A-Z][A-Z0-9_]{2,79}$",
    ),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CaseType(str, Enum):
    CHECKLIST = "checklist"


class ScenarioType(str, Enum):
    NORMAL = "normal"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    COMPATIBILITY = "compatibility"
    RECOVERY = "recovery"
    SECURITY = "security"


class TestPointCategory(str, Enum):
    FUNCTIONAL = "functional"
    RELIABILITY = "reliability"
    BOUNDARY = "boundary"
    COMPATIBILITY = "compatibility"
    RECOVERY = "recovery"
    SECURITY = "security"


class TestPoint(StrictModel):
    category: TestPointCategory
    title: ShortText
    description: PlainText
    priority: Priority


class TestCaseDraftData(StrictModel):
    suggested_code: SuggestedCode
    title: ShortText
    module: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ]
    priority: Priority
    case_type: CaseType
    precondition: OptionalLongText
    steps: RequiredLongText
    expected_result: RequiredLongText
    scenario_type: ScenarioType


class DraftEditInput(TestCaseDraftData):
    pass


class TestDesignResult(StrictModel):
    summary: SummaryText
    test_points: Annotated[list[TestPoint], Field(min_length=1, max_length=20)]
    case_drafts: Annotated[
        list[TestCaseDraftData],
        Field(min_length=1, max_length=20),
    ]
    limitations: Annotated[
        list[PlainText],
        Field(min_length=1, max_length=8),
    ]


class TestDesignContext(StrictModel):
    title: ShortText
    requirement_text: RequirementText


class QualityAssessment(StrictModel):
    quality_score: Annotated[int, Field(ge=0, le=100)]
    dimension_scores: dict[str, Annotated[int, Field(ge=0, le=25)]]
    missing_scenarios: list[ScenarioType]
    deduction_reasons: list[PlainText]
    risk_warnings: list[PlainText]
