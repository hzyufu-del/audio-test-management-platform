from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from .schemas import TestDesignContext, TestDesignResult


@dataclass(frozen=True)
class GenerationMetadata:
    """Bounded evidence fields only; unknown or malformed values stay absent."""

    provider_model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    input_chars: int | None = None
    output_chars: int | None = None

    def __post_init__(self):
        for field in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "max_tokens",
            "input_chars",
            "output_chars",
        ):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                object.__setattr__(self, field, None)
        for field, limit in (("provider_model", 120), ("finish_reason", 40)):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > limit
            ):
                object.__setattr__(self, field, None)
            else:
                object.__setattr__(self, field, value.strip())
        value = self.temperature
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
            or (isinstance(value, float) and not isfinite(value))
        ):
            object.__setattr__(self, "temperature", None)


class TestDesignProvider(ABC):
    provider_name = "unknown"
    provider_model = None
    is_demo = False
    last_call_metadata: GenerationMetadata | None = None

    @abstractmethod
    def generate(self, context: TestDesignContext) -> TestDesignResult:
        """Return a strictly validated test design without persisting it."""
