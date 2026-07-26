from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)


PositiveId = Annotated[int, Field(strict=True, gt=0)]
CodeText = Annotated[StrictStr, Field(min_length=1, max_length=80)]
TitleText = Annotated[StrictStr, Field(min_length=1, max_length=200)]
ModuleText = Annotated[StrictStr, Field(min_length=1, max_length=80)]
LongText = Annotated[StrictStr, Field(min_length=1, max_length=20000)]
OptionalLongText = Annotated[StrictStr, Field(max_length=20000)] | None
TesterText = Annotated[StrictStr, Field(min_length=1, max_length=80)]
EnvironmentText = Annotated[StrictStr, Field(max_length=120)] | None
DefectCodeText = Annotated[StrictStr, Field(min_length=1, max_length=40)]
PersonText = Annotated[StrictStr, Field(max_length=80)] | None
ResolutionText = Annotated[StrictStr, Field(max_length=80)] | None


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TestCaseCreateRequest(StrictRequestModel):
    version_id: PositiveId
    code: CodeText
    title: TitleText
    module: ModuleText
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    case_type: Literal["checklist"] = "checklist"
    precondition: OptionalLongText = None
    steps: LongText
    expected_result: LongText
    status: Literal["draft", "active", "archived"] = "draft"

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value):
        return value.upper()


class ExecutionCreateRequest(StrictRequestModel):
    test_case_id: PositiveId
    result: Literal["passed", "failed", "blocked", "skipped"]
    actual_result: OptionalLongText = None
    tester: TesterText
    environment: EnvironmentText = None
    executed_at: AwareDatetime | None = None
    notes: OptionalLongText = None

    @model_validator(mode="after")
    def validate_result_details(self):
        if self.result == "failed" and not self.actual_result:
            raise ValueError("failed 执行必须填写 actual_result")
        if (
            self.result == "blocked"
            and not self.actual_result
            and not self.notes
        ):
            raise ValueError(
                "blocked 执行必须填写 actual_result 或 notes"
            )
        return self


class DefectCreateRequest(StrictRequestModel):
    test_execution_id: PositiveId
    code: DefectCodeText
    title: TitleText
    description: LongText
    component: ModuleText
    severity: Literal["blocker", "critical", "major", "minor"] = "major"
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    status: Literal["open", "fixed", "closed", "rejected"] = "open"
    reproduction_steps: LongText
    observed_result: LongText
    reporter: TesterText
    assignee: PersonText = None
    resolution: ResolutionText = None
    resolution_note: OptionalLongText = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value):
        return value.upper()


class DefectPatchRequest(StrictRequestModel):
    status: Literal["open", "fixed", "closed", "rejected"] | None = None
    severity: Literal["blocker", "critical", "major", "minor"] | None = None
    priority: Literal["P0", "P1", "P2", "P3"] | None = None
    assignee: PersonText = None
    resolution: ResolutionText = None
    resolution_note: OptionalLongText = None

    @field_validator("status", "severity", "priority")
    @classmethod
    def reject_null_enums(cls, value):
        if value is None:
            raise ValueError("枚举字段不能为 null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.__pydantic_fields_set__:
            raise ValueError("至少提供一个可更新字段")
        return self
