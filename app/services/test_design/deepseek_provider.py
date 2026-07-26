import json
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

from .prompts import TEST_DESIGN_SYSTEM_PROMPT
from .provider import TestDesignProvider
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
            max_retries=1,
        )

    def generate(self, context: TestDesignContext) -> TestDesignResult:
        user_content = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            response = self.client.chat.completions.create(
                model=self.provider_model,
                messages=[
                    {
                        "role": "system",
                        "content": TEST_DESIGN_SYSTEM_PROMPT,
                    },
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=self.max_output_tokens,
                stream=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except APITimeoutError:
            raise AIProviderError(
                "AI test design request timed out. No draft was saved."
            ) from None
        except AuthenticationError:
            raise AIConfigurationError(
                "DeepSeek test design is not configured locally."
            ) from None
        except RateLimitError:
            raise AIProviderError(
                "AI test design is temporarily rate limited."
            ) from None
        except (APIConnectionError, APIStatusError):
            raise AIProviderError(
                "AI test design is temporarily unavailable."
            ) from None
        except Exception:
            raise AIProviderError(
                "AI test design is temporarily unavailable."
            ) from None

        content = self._response_content(response)
        try:
            return TestDesignResult.model_validate_json(
                self._remove_complete_json_wrapper(content)
            )
        except (ValidationError, ValueError, TypeError):
            raise AIResponseError(
                "AI test design output failed strict schema validation."
            ) from None

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
