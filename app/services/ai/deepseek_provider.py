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

from .exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
)
from .prompts import SYSTEM_PROMPT
from .provider import AIProvider
from .schemas import SemanticReviewResult, TestCaseReviewContext


class DeepSeekProvider(AIProvider):
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
        thinking_enabled=False,
        client_factory=OpenAI,
    ):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.base_url = self._validate_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.thinking_enabled = thinking_enabled

        if not self.api_key or not self.model:
            raise AIConfigurationError(
                "DeepSeek API 尚未配置，请设置本地环境变量。"
            )

        self.client = client_factory(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=1,
        )

    def review_test_case(
        self,
        context: TestCaseReviewContext,
    ) -> SemanticReviewResult:
        serialized_context = json.dumps(
            context.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": serialized_context},
                ],
                response_format={"type": "json_object"},
                max_tokens=self.max_output_tokens,
                stream=False,
                extra_body={
                    "thinking": {
                        "type": (
                            "enabled"
                            if self.thinking_enabled
                            else "disabled"
                        )
                    }
                },
            )
        except APITimeoutError:
            raise AIProviderError(
                "AI 请求超时，原有测试用例未受影响。"
            ) from None
        except AuthenticationError:
            raise AIConfigurationError(
                "DeepSeek API 尚未配置，请设置本地环境变量。"
            ) from None
        except RateLimitError:
            raise AIProviderError(
                "AI 服务请求过于频繁，请稍后重试。"
            ) from None
        except (APIConnectionError, APIStatusError):
            raise AIProviderError(
                "AI 服务暂时不可用，请稍后重试。"
            ) from None
        except Exception:
            raise AIProviderError(
                "AI 服务暂时不可用，请稍后重试。"
            ) from None

        content = self._response_content(response)
        payload_text = self._remove_complete_json_wrapper(content)
        try:
            payload = json.loads(payload_text)
            return SemanticReviewResult.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError):
            raise AIResponseError(
                "AI 返回结果无法通过结构校验。"
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
            raise AIConfigurationError("DeepSeek Base URL 配置无效。")
        return value.rstrip("/")

    @staticmethod
    def _response_content(response):
        choices = getattr(response, "choices", None)
        if not choices:
            raise AIResponseError("AI 返回了空内容，原有数据未发生变化。")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise AIResponseError("AI 返回了空内容，原有数据未发生变化。")
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise AIResponseError("AI 返回了空内容，原有数据未发生变化。")
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
