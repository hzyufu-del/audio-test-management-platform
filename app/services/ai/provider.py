from abc import ABC, abstractmethod

from .schemas import SemanticReviewResult, TestCaseReviewContext


class AIProvider(ABC):
    provider_name = "unknown"
    is_demo = False

    @abstractmethod
    def review_test_case(
        self,
        context: TestCaseReviewContext,
    ) -> SemanticReviewResult:
        """Return a strictly validated semantic review."""
