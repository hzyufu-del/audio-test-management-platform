"""Explicit single-attempt experiment adapters; dry-run belongs to the runner.

Construction requires execution permission but does not create a client or a
database. Every Proposed database is a new, isolated file. No app factory,
production seed, review action, environment loader, or implicit retry is used.
"""

import hashlib
import json
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from flask import Flask
from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy.engine import URL

from app.extensions import db
from app.models import GenerationRun, Project, TestCaseDraft, Version
from app.services.ai.exceptions import AIProviderError, AIResponseError
from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider
from app.services.test_design.diagnostics import sanitize_validation_summary, validation_summary
from app.services.test_design.evidence import safe_error, safe_text
from app.services.test_design.prompts import PROMPT_VERSION, prompt_hash, requirement_hash
from app.services.test_design.schemas import TestDesignContext, TestDesignResult
from app.services.test_design.security import contains_demo_scope, contains_forbidden_content
from app.services.test_design_service import TestDesignService


BASELINE_PROMPT_VERSION = "baseline-v1"
BASELINE_PROMPT = (
    "请根据以下虚构软件需求生成 3～6 条简洁测试用例，每条说明编号、标题、模块、"
    "优先级、用例类型、场景类型、前置条件、测试步骤和预期结果，以清晰列表输出。"
    "标题和需求如下。"
)
_ROOT = Path(__file__).resolve().parents[1]
_CASE_FIELDS = (
    "suggested_code", "title", "module", "priority", "case_type", "scenario_type",
    "precondition", "steps", "expected_result",
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _baseline_messages(context):
    return [{"role": "user", "content": BASELINE_PROMPT + "\n" + _canonical(context)}]


def baseline_prompt_hash():
    template = _baseline_messages({"title": "{title}", "requirement_text": "{requirement_text}"})
    return hashlib.sha256(_canonical(template).encode("utf-8")).hexdigest()


def _utc(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _counter(value):
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _settings(values):
    if not isinstance(values, dict):
        raise ValueError("Explicit experiment settings are required.")
    if values.get("execute") is not True or values.get("ai_enabled") is not True:
        raise ValueError("Explicit execution and AI enablement are required.")
    result = dict(values)
    for field in ("api_key", "model"):
        value = result.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Experiment credentials and requested model are required.")
        result[field] = value.strip()
    secret = result.get("secret_key", "")
    if not isinstance(secret, str):
        raise ValueError("Experiment secret settings are invalid.")
    result["secret_key"] = secret.strip()
    for field, minimum, maximum in (("timeout_seconds", 1, 120), ("max_output_tokens", 100, 8000)):
        value = result.get(field)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError("Experiment timeout or output budget is invalid.")
    try:
        result["base_url"] = DeepSeekTestDesignProvider._validate_base_url(result.get("base_url"))
    except Exception:
        raise ValueError("Experiment endpoint is invalid.") from None
    config = _config(result)
    if safe_text(result["model"], 120, config) is None:
        raise ValueError("Experiment requested model is invalid.")
    return result


def _config(settings):
    return {
        "SECRET_KEY": settings["secret_key"], "DEEPSEEK_API_KEY": settings["api_key"],
        "DEEPSEEK_MODEL": settings["model"], "DEEPSEEK_BASE_URL": settings["base_url"],
        "AI_ENABLED": True, "AI_PROVIDER": "deepseek", "DEEPSEEK_THINKING_ENABLED": False,
        "AI_REQUEST_TIMEOUT_SECONDS": settings["timeout_seconds"],
        "AI_MAX_OUTPUT_TOKENS": settings["max_output_tokens"],
    }


def _unsafe(value, config):
    if contains_forbidden_content(value, config=config):
        return True
    # The baseline template is public, but copying it is still prompt leakage.
    if isinstance(value, str):
        return BASELINE_PROMPT in value
    if isinstance(value, dict):
        return any(_unsafe(item, config) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_unsafe(item, config) for item in value)
    return False


def _context(requirement, config):
    if not isinstance(requirement, dict):
        raise ValueError("Invalid requirement.")
    try:
        context = TestDesignContext(title=requirement.get("title"),
                                    requirement_text=requirement.get("requirement_text"))
    except (ValidationError, TypeError):
        raise ValueError("Invalid requirement.") from None
    if _unsafe(context.model_dump(mode="json"), config) or not contains_demo_scope(context.requirement_text):
        raise ValueError("Invalid requirement.")
    return context


def _record(settings, version, template_hash, scope):
    return {
        "status": "pre_call_failed", "provider": "deepseek",
        "requested_model": settings["model"], "returned_model": None,
        "model_evidence_source": "response_model_unavailable", "provider_model": None,
        "prompt_version": version, "prompt_hash": template_hash, "requirement_hash": None,
        "started_at": _utc(), "finished_at": None, "latency_ms": None, "latency_scope": scope,
        "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
        "finish_reason": None, "input_chars": None, "output_chars": None,
        "error_type": None, "error_message": None, "initial_text": None,
        "initial_cases": [], "structured_output": None, "generation_run_id": None,
        "session_id": None, "project_id": None, "version_id": None,
    }


def _failure(record, status, error_type, message):
    record.update(status=status, error_type=error_type, error_message=message, finished_at=_utc())
    return record


def _response_evidence(record, model, config):
    record["returned_model"] = safe_text(model, 120, config)
    if record["returned_model"] is not None:
        record["model_evidence_source"] = "provider_response_metadata"


class _TrackedProvider(DeepSeekTestDesignProvider):
    """Track invocation separately from the audit row created before it."""

    call_started = False

    def __init__(self, *, experiment_config, **kwargs):
        super().__init__(**kwargs)
        self.experiment_config = experiment_config

    def generate(self, context):
        self.call_started = True
        result = super().generate(context)
        if _unsafe(result.model_dump(mode="json"), self.experiment_config):
            self.last_validation_summary = validation_summary("output_safety", "sensitive_content")
            raise AIResponseError("Experiment output failed safety validation.")
        return result


class _Adapter:
    def __init__(self, settings, client_factory):
        self.settings = _settings(settings)
        self.config = _config(self.settings)
        self._client_factory = client_factory
        self._clients = []
        self._closed = False

    def _client(self):
        # Resolve now, so an injected/monkeypatched factory cannot be frozen in
        # a default argument and silently replaced with a real network client.
        factory = self._client_factory if self._client_factory is not None else OpenAI
        client = factory(api_key=self.settings["api_key"], base_url=self.settings["base_url"],
                         timeout=self.settings["timeout_seconds"], max_retries=0)
        self._clients.append(client)
        return client

    def close(self):
        if self._closed:
            return
        self._closed = True
        for client in self._clients:
            close = getattr(client, "close", None)
            if callable(close):
                # Cleanup must not expose an SDK exception or secret.
                with suppress(Exception):
                    close()
        self._clients.clear()


class BaselineAdapter(_Adapter):
    def __init__(self, settings: dict, client_factory=None):
        super().__init__(settings, client_factory)

    def generate(self, requirement: dict) -> dict:
        record = _record(self.settings, BASELINE_PROMPT_VERSION, baseline_prompt_hash(),
                         "baseline_adapter_including_validation")
        try:
            if self._closed:
                raise ValueError("Closed adapter.")
            context = _context(requirement, self.config)
            record["requirement_hash"] = requirement_hash(context.requirement_text)
            messages = _baseline_messages(context.model_dump(mode="json"))
            record["input_chars"] = sum(len(item["content"]) for item in messages)
            client = self._client()
        except Exception:
            return _failure(record, "pre_call_failed", "AIConfigurationError",
                            "Experiment input or client preparation failed before the call.")
        started = perf_counter()
        try:
            response = client.chat.completions.create(
                model=self.settings["model"], messages=messages,
                max_tokens=self.settings["max_output_tokens"], stream=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
            usage = getattr(response, "usage", None)
            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                record[field] = _counter(getattr(usage, field, None))
            _response_evidence(record, getattr(response, "model", None), self.config)
            choices = getattr(response, "choices", None)
            choice = choices[0] if choices else None
            record["finish_reason"] = safe_text(getattr(choice, "finish_reason", None), 40, self.config)
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None)
            record["output_chars"] = len(content) if isinstance(content, str) else None
            if record["finish_reason"] == "length":
                raise AIResponseError("Output was truncated.")
            if not isinstance(content, str) or not content.strip() or _unsafe(content, self.config):
                raise AIResponseError("Output was unsafe or empty.")
            record.update(status="succeeded", initial_text=content)
        except Exception as exc:
            error_type, message = safe_error(exc)
            _failure(record, "failed", error_type, message)
        finally:
            record["latency_ms"] = max(0, round((perf_counter() - started) * 1000))
            record["finished_at"] = _utc()
        return record


class ProposedAdapter(_Adapter):
    def __init__(self, settings: dict, database_path: Path, client_factory=None):
        super().__init__(settings, client_factory)
        self.database_path = Path(database_path).resolve()
        instance = (_ROOT / "instance").resolve()
        if (self.database_path == instance or instance in self.database_path.parents
                or self.database_path.exists()
                or self.database_path.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}
                or (_ROOT in self.database_path.parents
                    and (_ROOT / "experiment").resolve() not in self.database_path.parents)):
            raise ValueError("A new isolated experiment database path is required.")
        self._app = None
        self._project_id = None
        self._attempts = 0

    def _database(self):
        if self._app is not None:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # Reserve exclusively immediately before connecting; constructor-only
        # checks would allow a concurrent file to be opened or overwritten.
        with self.database_path.open("xb"):
            pass
        app = Flask("experiment_proposed", instance_path=str(self.database_path.parent),
                    instance_relative_config=True)
        app.config.update(self.config)
        app.config.update(SQLALCHEMY_DATABASE_URI=URL.create("sqlite", database=str(self.database_path)),
                          SQLALCHEMY_TRACK_MODIFICATIONS=False)
        db.init_app(app)
        self._app = app
        with app.app_context():
            db.create_all()
            project = Project(name="Demo isolated experiment", code="DEMO-EXPERIMENT")
            db.session.add(project)
            db.session.commit()
            self._project_id = project.id

    def _provider(self):
        provider = _TrackedProvider(
            experiment_config=self.config,
            api_key=self.settings["api_key"], model=self.settings["model"],
            base_url=self.settings["base_url"], timeout_seconds=self.settings["timeout_seconds"],
            max_output_tokens=self.settings["max_output_tokens"],
            client_factory=lambda **kwargs: self._client(),
        )
        return provider

    def _export(self, record, run, context, version_id):
        record.update(generation_run_id=run.id, session_id=run.session_id,
                      project_id=run.project_id, version_id=run.version_id,
                      status=run.status, run_status=run.status, provider_model=run.provider_model,
                      prompt_version=run.prompt_version, prompt_hash=run.prompt_hash,
                      requirement_hash=run.requirement_hash, started_at=_utc(run.started_at),
                      finished_at=_utc(run.finished_at) if run.finished_at else None,
                      latency_ms=_counter(run.latency_ms), error_type=run.error_type,
                      error_message=run.error_message)
        for field in ("prompt_tokens", "completion_tokens", "total_tokens", "input_chars", "output_chars"):
            record[field] = _counter(getattr(run, field))
        record["finish_reason"] = safe_text(run.finish_reason, 40, self.config)
        if (run.project_id != self._project_id or run.version_id != version_id
                or run.title != context.title or run.requirement_text != context.requirement_text
                or run.requirement_hash != requirement_hash(context.requirement_text)
                or run.prompt_version != PROMPT_VERSION or run.prompt_hash != prompt_hash()
                or run.provider != "deepseek"):
            raise ValueError("Generation evidence does not match this attempt.")
        if run.structured_output_json:
            snapshot = TestDesignResult.model_validate_json(run.structured_output_json).model_dump(mode="json")
            if _unsafe(snapshot, self.config):
                raise ValueError("Unsafe generation evidence.")
            record["structured_output"] = snapshot
        if run.status != "succeeded":
            return
        if record["structured_output"] is None or run.session_id is None:
            raise ValueError("Successful generation evidence is incomplete.")
        session = run.session
        if (session is None or session.project_id != run.project_id or session.version_id != version_id
                or session.title != context.title or session.requirement_text != context.requirement_text
                or session.provider != "deepseek" or session.prompt_version != run.prompt_version):
            raise ValueError("Session source does not match the attempt.")
        rows = TestCaseDraft.query.filter_by(generation_run_id=run.id).order_by(TestCaseDraft.id).all()
        cases = []
        for draft in rows:
            if (draft.session_id != run.session_id or draft.status != "pending"
                    or draft.accepted_test_case_id is not None):
                raise ValueError("Draft source or initial state is invalid.")
            case = {field: getattr(draft, field) for field in _CASE_FIELDS}
            case["precondition"] = case["precondition"] or ""
            cases.append({**case, "draft_id": draft.id, "generation_run_id": draft.generation_run_id,
                          "session_id": draft.session_id, "status": draft.status,
                          "accepted_test_case_id": draft.accepted_test_case_id})
        content = [{field: case[field] for field in _CASE_FIELDS} for case in cases]
        expected = record["structured_output"]["case_drafts"]
        if sorted(map(_canonical, content)) != sorted(map(_canonical, expected)):
            raise ValueError("Draft contents differ from the initial snapshot.")
        if (json.loads(session.test_points_json) != record["structured_output"]["test_points"]
                or json.loads(session.limitations_json) != record["structured_output"]["limitations"]
                or _unsafe(cases, self.config)):
            raise ValueError("Session contents differ from the initial snapshot.")
        record["initial_cases"] = cases

    def generate(self, requirement: dict) -> dict:
        record = _record(self.settings, PROMPT_VERSION, prompt_hash(), "test_design_service")
        try:
            if self._closed:
                raise ValueError("Closed adapter.")
            context = _context(requirement, self.config)
            record["requirement_hash"] = requirement_hash(context.requirement_text)
            self._database()
        except Exception:
            return _failure(record, "pre_call_failed", "AIConfigurationError",
                            "Experiment input or isolated database preparation failed before the call.")
        provider = None
        error = None
        with self._app.app_context():
            try:
                self._attempts += 1
                version = Version(project_id=self._project_id, name="Demo generation attempt",
                                  code=f"ATTEMPT-{self._attempts:04d}")
                db.session.add(version)
                db.session.commit()
                version_id = version.id
                record.update(project_id=self._project_id, version_id=version_id)
                before = {run.id for run in GenerationRun.query.filter_by(version_id=version_id).all()}
                provider = self._provider()
                TestDesignService(self.config, provider=provider).create_session(
                    project_id=self._project_id, version_id=version_id,
                    title=context.title, requirement_text=context.requirement_text,
                )
            except Exception as exc:
                error = exc
                db.session.rollback()
            if provider is not None:
                metadata = getattr(provider, "last_call_metadata", None)
                _response_evidence(record, getattr(metadata, "provider_model", None), self.config)
                if self.settings.get("validation_diagnostics") is True:
                    diagnostic = sanitize_validation_summary(
                        getattr(provider, "last_validation_summary", None))
                    if diagnostic is not None:
                        record["validation_diagnostic"] = diagnostic
            try:
                if record["version_id"] is None:
                    raise ValueError("No experiment version was created.")
                db.session.expire_all()
                new_runs = [run for run in GenerationRun.query.filter_by(version_id=record["version_id"]).all()
                            if run.id not in before]
                if len(new_runs) != 1:
                    status = "failed" if provider is not None and provider.call_started else "pre_call_failed"
                    error_type, message = safe_error(error or AIProviderError("Missing call evidence."))
                    return _failure(record, status, error_type, message)
                self._export(record, new_runs[0], context, record["version_id"])
            except Exception:
                record.update(initial_cases=[], structured_output=None)
                status = "failed" if provider is not None and provider.call_started else "pre_call_failed"
                return _failure(record, status, "EvidenceValidationError",
                                "Experiment evidence could not be verified safely.")
        return record

    def close(self):
        super().close()
        if self._app is not None:
            with self._app.app_context():
                db.session.remove()
                db.engine.dispose()
