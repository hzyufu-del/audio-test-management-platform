import json

from pydantic import ValidationError

from .ai.deepseek_provider import DeepSeekProvider
from .ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
    AIReviewDisabledError,
    AIReviewError,
)
from .ai.mock_provider import MockAIProvider
from .ai.schemas import (
    IssueCategory,
    IssueSeverity,
    ProjectReviewContext,
    SemanticReviewResult,
    TestCaseReviewContext,
    TestCaseReviewResult,
    TestCaseSnapshot,
    VersionReviewContext,
)
from .testcase_review_rules import normalize_review_text, review_test_case_rules


SEVERITY_DEDUCTIONS = {
    IssueSeverity.CRITICAL: 20,
    IssueSeverity.WARNING: 10,
    IssueSeverity.INFO: 3,
}
EXTRA_CATEGORY_DEDUCTIONS = {
    IssueCategory.MISSING_PRECONDITION: 10,
    IssueCategory.UNVERIFIABLE_EXPECTATION: 10,
    IssueCategory.DUPLICATE_STEP: 8,
    IssueCategory.STEP_EXPECTATION_MISMATCH: 12,
}
EMPTY_FIELD_DEDUCTIONS = {
    "steps": 30,
    "expected_result": 30,
}
FIELD_LIMITS = {
    ("test_case", "title"): 500,
    ("test_case", "code"): 100,
    ("test_case", "module"): 200,
    ("test_case", "priority"): 20,
    ("test_case", "case_type"): 40,
    ("test_case", "precondition"): 2500,
    ("test_case", "steps"): 7000,
    ("test_case", "expected_result"): 5000,
    ("test_case", "status"): 30,
    ("version", "name"): 500,
    ("version", "code"): 100,
    ("version", "status"): 30,
    ("project", "name"): 500,
    ("project", "code"): 100,
}
MINIMUM_FIELD_LENGTHS = {
    ("test_case", "title"): 50,
    ("test_case", "code"): 20,
    ("test_case", "module"): 20,
    ("test_case", "priority"): 5,
    ("test_case", "case_type"): 10,
    ("test_case", "precondition"): 100,
    ("test_case", "steps"): 100,
    ("test_case", "expected_result"): 100,
    ("test_case", "status"): 10,
    ("version", "name"): 20,
    ("version", "code"): 20,
    ("version", "status"): 10,
    ("project", "name"): 20,
    ("project", "code"): 20,
}


class TestCaseAIService:
    def __init__(self, config, provider=None):
        self.config = config
        self.provider = provider

    def review_test_case(self, test_case):
        if not self.config.get("AI_ENABLED", False):
            raise AIReviewDisabledError("AI 审查当前未启用。")

        context, input_limitations = self.build_provider_context(test_case)
        rule_issues = review_test_case_rules(context.test_case)
        provider = self.provider or self._create_provider()

        try:
            raw_semantic_review = provider.review_test_case(context)
        except AIReviewError:
            raise
        except Exception:
            raise AIProviderError(
                "AI 服务暂时不可用，请稍后重试。"
            ) from None

        try:
            semantic_review = SemanticReviewResult.model_validate(
                raw_semantic_review
            )
        except ValidationError:
            raise AIResponseError(
                "AI 返回结果无法通过结构校验。"
            ) from None

        semantic_review = self._merge_and_deduplicate(
            rule_issues,
            semantic_review,
            input_limitations,
        )
        quality_score = self._calculate_quality_score(
            context,
            rule_issues,
            semantic_review.issues,
        )
        return TestCaseReviewResult(
            quality_score=quality_score,
            rule_issues=rule_issues,
            semantic_review=semantic_review,
            provider_name=provider.provider_name,
            is_demo=provider.is_demo,
        )

    def build_provider_context(self, test_case):
        data = {
            "test_case": {
                "title": self._normalize_field(test_case.title),
                "code": self._normalize_field(test_case.code),
                "module": self._normalize_field(test_case.module),
                "priority": self._normalize_field(test_case.priority),
                "case_type": self._normalize_field(test_case.case_type),
                "precondition": self._normalize_field(test_case.precondition),
                "steps": self._normalize_field(test_case.steps),
                "expected_result": self._normalize_field(
                    test_case.expected_result
                ),
                "status": self._normalize_field(test_case.status),
            },
            "version": {
                "name": self._normalize_field(test_case.version.name),
                "code": self._normalize_field(test_case.version.code),
                "status": self._normalize_field(test_case.version.status),
            },
            "project": {
                "name": self._normalize_field(test_case.version.project.name),
                "code": self._normalize_field(test_case.version.project.code),
            },
        }
        limitations = []
        field_truncated = False
        for path, limit in FIELD_LIMITS.items():
            value = self._nested_value(data, path)
            if len(value) > limit:
                self._set_nested_value(data, path, self._truncate(value, limit))
                field_truncated = True
        if field_truncated:
            limitations.append("Provider 输入因单字段长度限制被截断。")

        max_input_chars = int(self.config.get("AI_MAX_INPUT_CHARS", 12000))
        if self._fit_total_length(data, max_input_chars):
            limitations.append(
                "Provider 输入因 AI_MAX_INPUT_CHARS 限制被截断。"
            )

        context = TestCaseReviewContext(
            test_case=TestCaseSnapshot(**data["test_case"]),
            version=VersionReviewContext(**data["version"]),
            project=ProjectReviewContext(**data["project"]),
        )
        return context, limitations

    def _create_provider(self):
        provider_name = self.config.get("AI_PROVIDER", "mock")
        if provider_name == "mock":
            return MockAIProvider()
        if provider_name == "deepseek":
            return DeepSeekProvider(
                api_key=self.config.get("DEEPSEEK_API_KEY", ""),
                model=self.config.get("DEEPSEEK_MODEL", ""),
                base_url=self.config.get(
                    "DEEPSEEK_BASE_URL",
                    "https://api.deepseek.com",
                ),
                timeout_seconds=self.config.get(
                    "AI_REQUEST_TIMEOUT_SECONDS",
                    20,
                ),
                max_output_tokens=self.config.get(
                    "AI_MAX_OUTPUT_TOKENS",
                    2000,
                ),
                thinking_enabled=self.config.get(
                    "DEEPSEEK_THINKING_ENABLED",
                    False,
                ),
            )
        raise AIConfigurationError(
            "AI_PROVIDER 配置无效，只允许 mock 或 deepseek。"
        )

    @staticmethod
    def _normalize_field(value):
        lines = [
            normalize_review_text(line)
            for line in str(value or "").splitlines()
        ]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def _truncate(value, limit):
        if len(value) <= limit:
            return value
        if limit <= 1:
            return value[:limit]
        return f"{value[: limit - 1]}…"

    def _fit_total_length(self, data, max_chars):
        was_truncated = False
        while self._serialized_length(data) > max_chars:
            overflow = self._serialized_length(data) - max_chars
            candidates = []
            for path, minimum in MINIMUM_FIELD_LENGTHS.items():
                value = self._nested_value(data, path)
                reducible = len(value) - minimum
                if reducible > 0:
                    candidates.append((reducible, path, value, minimum))
            if not candidates:
                raise AIConfigurationError(
                    "AI_MAX_INPUT_CHARS 无法容纳最小 Provider 输入。"
                )
            _, path, value, minimum = max(candidates, key=lambda item: item[0])
            reduction = min(len(value) - minimum, max(overflow, 1))
            new_limit = len(value) - reduction
            self._set_nested_value(data, path, self._truncate(value, new_limit))
            was_truncated = True
        return was_truncated

    @staticmethod
    def _serialized_length(data):
        return len(
            json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @staticmethod
    def _nested_value(data, path):
        return data[path[0]][path[1]]

    @staticmethod
    def _set_nested_value(data, path, value):
        data[path[0]][path[1]] = value

    @staticmethod
    def _merge_and_deduplicate(
        rule_issues,
        semantic_review,
        input_limitations,
    ):
        seen = {_issue_key(issue) for issue in rule_issues}
        semantic_issues = []
        for issue in semantic_review.issues:
            key = _issue_key(issue)
            if key in seen:
                continue
            seen.add(key)
            semantic_issues.append(issue)

        limitations = _unique_strings(
            [*input_limitations, *semantic_review.limitations]
        )[:8]
        payload = semantic_review.model_dump()
        payload["issues"] = semantic_issues
        payload["limitations"] = limitations
        return SemanticReviewResult.model_validate(payload)

    @staticmethod
    def _calculate_quality_score(context, rule_issues, semantic_issues):
        unique_issues = []
        seen = set()
        for issue in [*rule_issues, *semantic_issues]:
            key = _issue_key(issue)
            if key in seen:
                continue
            seen.add(key)
            unique_issues.append(issue)

        score = 100
        for issue in unique_issues:
            score -= SEVERITY_DEDUCTIONS[issue.severity]

        present_categories = {issue.category for issue in unique_issues}
        for category, deduction in EXTRA_CATEGORY_DEDUCTIONS.items():
            if category in present_categories:
                score -= deduction

        test_case = context.test_case
        for field_name, deduction in EMPTY_FIELD_DEDUCTIONS.items():
            if not getattr(test_case, field_name):
                score -= deduction
        return max(0, min(100, score))


def _issue_key(issue):
    return (
        issue.category.value,
        normalize_review_text(issue.evidence).casefold(),
    )


def _unique_strings(values):
    seen = set()
    unique = []
    for value in values:
        key = normalize_review_text(value).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
