"""Persist bounded call evidence independently of the business transaction."""

import math

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import GenerationRun, utc_now
from app.services.ai.exceptions import (
    AIConfigurationError, AIResponseError, AIReviewDisabledError,
)
from app.services.workflow_errors import WorkflowPersistenceError

from .prompts import PROMPT_VERSION, build_test_design_messages, prompt_hash, requirement_hash
from .security import contains_forbidden_content


def safe_error(exc):
    # Never serialize an SDK exception: even apparently safe messages can
    # include arbitrary header values, request content or environment secrets.
    messages = {
        AIResponseError: "AI test design output failed validation.",
        AIConfigurationError: "DeepSeek test design is not configured locally.",
        AIReviewDisabledError: "DeepSeek test design is disabled.",
        WorkflowPersistenceError: "Generated test design could not be saved.",
    }
    for error_class, message in messages.items():
        if isinstance(exc, error_class):
            return error_class.__name__, message
    return "AIProviderError", "AI test design is temporarily unavailable."


def safe_metadata(provider, config):
    metadata = getattr(provider, "last_call_metadata", None)
    values = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens",
                 "input_chars", "output_chars", "max_tokens"):
        value = getattr(metadata, name, None)
        values[name] = value if type(value) is int and 0 <= value <= 2**63 - 1 else None
    for name, maximum in (("provider_model", 120), ("finish_reason", 40)):
        value = getattr(metadata, name, None)
        values[name] = safe_text(value, maximum, config)
    values["provider_model"] = values["provider_model"] or safe_text(
        getattr(provider, "provider_model", None), 120, config,
    )
    temperature = getattr(metadata, "temperature", None)
    values["temperature"] = (
        temperature if type(temperature) in (int, float)
        and 0 <= temperature <= 2 and math.isfinite(temperature) else None
    )
    return values


def safe_text(value, maximum, config):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        return None
    if contains_forbidden_content(value, config=config):
        return None
    return value.strip()


class GenerationRecorder:
    def __init__(self, config):
        self.config = config

    def start(self, *, context, project_id, version_id, provider, session_id=None):
        provider_name = getattr(provider, "provider_name", "unknown")
        if provider_name not in {"mock", "deepseek"}:
            raise AIConfigurationError("Unknown test design provider.")
        messages = build_test_design_messages(context)
        values = safe_metadata(provider, self.config)
        run = GenerationRun(
            session_id=session_id, project_id=project_id, version_id=version_id,
            title=context.title, requirement_text=context.requirement_text,
            provider=provider_name, provider_model=values["provider_model"],
            prompt_version=PROMPT_VERSION, prompt_hash=prompt_hash(),
            requirement_hash=requirement_hash(context.requirement_text),
            status="running", started_at=utc_now(),
            input_chars=sum(len(message["content"]) for message in messages),
            max_tokens=(getattr(provider, "max_output_tokens", None)
                        if provider_name == "deepseek" else None),
        )
        try:
            with Session(bind=db.engine, expire_on_commit=False) as audit:
                audit.add(run)
                audit.commit()
                return run.id
        except SQLAlchemyError:
            raise WorkflowPersistenceError(
                "Generation evidence could not be saved. No model call was made."
            ) from None

    def fail(self, run_id, *, error, metadata, latency_ms, structured_output_json=None):
        error_type, error_message = safe_error(error)
        try:
            with Session(bind=db.engine) as audit:
                run = audit.get(GenerationRun, run_id)
                run.status = "failed"
                run.finished_at = utc_now()
                run.latency_ms = latency_ms
                # Keep the actual input length already computed on start if a
                # third-party Provider does not implement metadata.
                for name, value in metadata.items():
                    if value is not None:
                        setattr(run, name, value)
                run.error_type = error_type
                run.error_message = error_message
                run.structured_output_json = structured_output_json
                audit.commit()
        except SQLAlchemyError:
            raise WorkflowPersistenceError(
                "The call was recorded, but its final evidence could not be saved."
            ) from None
