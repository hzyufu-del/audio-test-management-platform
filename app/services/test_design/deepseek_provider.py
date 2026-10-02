from urllib.parse import urlsplit

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from app.services.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
)

from .prompts import build_test_design_messages
from .diagnostics import summarize_validation_error, validation_summary
from .provider import GenerationMetadata, TestDesignProvider
from .schemas import TestDesignContext, TestDesignResult


class DeepSeekTestDesignProvider(TestDesignProvider):
    provider_name = "deepseek"
    is_demo = False

    def __init__(
        self,
        *,
        api_key,
        model,
        base_url,
        timeout_seconds,
        max_output_tokens,
        client_factory=OpenAI,
    ):
        self.api_key = (api_key or "").strip()
        self.provider_model = (model or "").strip()
        self.base_url = self._validate_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

        if not self.api_key or not self.provider_model:
            raise AIConfigurationError(
                "DeepSeek test design is not configured locally."
            )

        self.client = client_factory(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

    def generate(self, context: TestDesignContext) -> TestDesignResult:
        self.last_call_metadata = None
        self.last_validation_summary = None
        messages = build_test_design_messages(context)
        input_chars = sum(len(item["content"]) for item in messages)
        self.last_call_metadata = GenerationMetadata(
            input_chars=input_chars,
            max_tokens=self.max_output_tokens,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.provider_model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=self.max_output_tokens,
                stream=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except APITimeoutError:
            self.last_validation_summary = validation_summary("api", "api_timeout")
            raise AIProviderError(
                "AI test design request timed out. No draft was saved."
            ) from None
        except AuthenticationError:
            self.last_validation_summary = validation_summary("api", "api_authentication")
            raise AIConfigurationError(
                "DeepSeek test design is not configured locally."
            ) from None
        except RateLimitError:
            self.last_validation_summary = validation_summary("api", "api_rate_limit")
            raise AIProviderError(
                "AI test design is temporarily rate limited."
            ) from None
        except (APIConnectionError, APIStatusError):
            self.last_validation_summary = validation_summary("api", "api_unavailable")
            raise AIProviderError(
                "AI test design is temporarily unavailable."
            ) from None
        except Exception:
            self.last_validation_summary = validation_summary("api", "api_unavailable")
            raise AIProviderError(
                "AI test design is temporarily unavailable."
            ) from None

        self.last_call_metadata = self._response_metadata(response, input_chars)
        if self.last_call_metadata.finish_reason == "length":
            self.last_validation_summary = validation_summary("output_limit", "output_limit")
            raise AIResponseError(
                "AI test design reached its output limit. No draft was saved."
            ) from None
        try:
            content = self._response_content(response)
        except AIResponseError:
            self.last_validation_summary = validation_summary("response_content", "no_usable_content")
            raise
        try:
            return TestDesignResult.model_validate_json(
                self._remove_complete_json_wrapper(content)
            )
        except ValidationError as exc:
            self.last_validation_summary = summarize_validation_error(exc)
            raise AIResponseError(
                "AI test design output failed strict schema validation."
            ) from None
        except (ValueError, TypeError):
            self.last_validation_summary = validation_summary("schema", "other")
            raise AIResponseError(
                "AI test design output failed strict schema validation."
            ) from None

    def _response_metadata(self, response, input_chars):
        usage = getattr(response, "usage", None)
        choices = getattr(response, "choices", None)
        choice = choices[0] if choices else None
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        return GenerationMetadata(
            provider_model=getattr(response, "model", None),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            finish_reason=getattr(choice, "finish_reason", None),
            max_tokens=self.max_output_tokens,
            input_chars=input_chars,
            output_chars=len(content) if isinstance(content, str) else None,
        )

    @staticmethod
    def _validate_base_url(base_url):
        value = (base_url or "").strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise AIConfigurationError("DeepSeek Base URL is invalid.")
        return value.rstrip("/")

    @staticmethod
    def _response_content(response):
        choices = getattr(response, "choices", None)
        if not choices:
            raise AIResponseError(
                "AI test design returned no usable content."
            )
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message else None
        if not isinstance(content, str) or not content.strip():
            raise AIResponseError(
                "AI test design returned no usable content."
            )
        return content.strip()

    @staticmethod
    def _remove_complete_json_wrapper(content):
        lines = content.splitlines()
        if (
            len(lines) >= 3
            and lines[0].strip().lower() in {"```", "```json"}
            and lines[-1].strip() == "```"
        ):
            return "\n".join(lines[1:-1]).strip()
        return content
