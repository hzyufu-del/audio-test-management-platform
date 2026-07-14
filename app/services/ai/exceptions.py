class AIReviewError(RuntimeError):
    """Base error whose message is safe to display to an end user."""


class AIReviewDisabledError(AIReviewError):
    """Raised when the optional AI review path is disabled."""


class AIConfigurationError(AIReviewError):
    """Raised when required local provider settings are invalid or missing."""


class AIProviderError(AIReviewError):
    """Raised when an AI provider request cannot be completed safely."""


class AIResponseError(AIReviewError):
    """Raised when an AI response is empty or fails strict validation."""
