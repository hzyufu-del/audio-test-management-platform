from abc import ABC, abstractmethod

from .schemas import TestDesignContext, TestDesignResult


class TestDesignProvider(ABC):
    provider_name = "unknown"
    provider_model = None
    is_demo = False

    @abstractmethod
    def generate(self, context: TestDesignContext) -> TestDesignResult:
        """Return a strictly validated test design without persisting it."""
