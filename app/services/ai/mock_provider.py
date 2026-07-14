from .provider import AIProvider
from .schemas import (
    IssueCategory,
    IssueSeverity,
    ReviewConfidence,
    SemanticReviewResult,
    TestCaseQualityIssue,
    TestCaseReviewContext,
)


class MockAIProvider(AIProvider):
    provider_name = "mock"
    is_demo = True

    def review_test_case(
        self,
        context: TestCaseReviewContext,
    ) -> SemanticReviewResult:
        test_case = context.test_case
        combined = " ".join(
            (
                test_case.title,
                test_case.precondition,
                test_case.steps,
                test_case.expected_result,
            )
        ).casefold()
        missing_scenarios = []
        if not any(marker in combined for marker in ("正常", "normal", "success")):
            missing_scenarios.append("补充一个可观察的正常流程场景。")
        if not any(
            marker in combined
            for marker in ("异常", "失败", "错误", "exception", "failure")
        ):
            missing_scenarios.append("补充一个失败或异常处理场景。")
        if not any(
            marker in combined
            for marker in ("边界", "最大", "最小", "boundary", "limit")
        ):
            missing_scenarios.append("补充一个输入或状态边界场景。")

        missing_preconditions = []
        if not test_case.precondition:
            missing_preconditions.append("明确 mock 设备、版本或环境的初始状态。")

        return SemanticReviewResult(
            summary="Demo AI Review 已完成确定性的语义提示生成。",
            issues=[
                TestCaseQualityIssue(
                    category=IssueCategory.REQUIREMENT_UNCERTAINTY,
                    severity=IssueSeverity.INFO,
                    description="无法仅根据用例文本确认需求覆盖是否完整。",
                    evidence="未向 Demo Provider 提供源需求或设计规格。",
                    suggestion="由测试人员结合需求与评审记录确认覆盖范围。",
                )
            ],
            missing_preconditions=missing_preconditions,
            ambiguous_expectations=[],
            missing_test_scenarios=missing_scenarios,
            rewrite_suggestions=[
                "为每个步骤补充可观察的对象、状态或数值结果。"
            ],
            confidence=ReviewConfidence.MEDIUM,
            limitations=[
                "这是完全离线且确定性的 Mock Provider，不代表真实模型判断。"
            ],
        )
