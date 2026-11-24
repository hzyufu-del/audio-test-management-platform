import secrets
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import GenerationRun, TestCaseDraft as Draft, TestDesignSession as Design
from app.services.ai.exceptions import AIConfigurationError, AIProviderError
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design_service import TestDesignService as Service
from app.services.workflow_errors import WorkflowConflictError


def data(catalog, **overrides):
    return {
        "project_id": catalog["first_project_id"],
        "version_id": catalog["first_version_id"],
        "title": "Demo submission safety",
        "requirement_text": "Sample audio volume adjustment for a mock connected device.",
        **overrides,
    }


class CountingProvider(MockTestDesignProvider):
    def __init__(self):
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        return super().generate(context)


def test_success_replay_reuses_one_run_and_one_session(api_app, api_catalog):
    with api_app.app_context():
        provider = CountingProvider()
        service = Service(api_app.config, provider)
        request = data(api_catalog, request_key=secrets.token_urlsafe(32))
        original = service.create_session(**request)
        repeated = service.create_session(**request)
        assert repeated.id == original.id
        assert provider.calls == GenerationRun.query.count() == Design.query.count() == 1
        assert GenerationRun.query.one().active_request_scope is None


def test_same_key_changed_input_is_conflict_without_call(api_app, api_catalog):
    with api_app.app_context():
        provider = CountingProvider()
        service = Service(api_app.config, provider)
        request = data(api_catalog, request_key=secrets.token_urlsafe(32))
        service.create_session(**request)
        with pytest.raises(WorkflowConflictError, match="different input"):
            service.create_session(**{**request, "title": "Different demo requirement"})
        assert provider.calls == GenerationRun.query.count() == 1


def test_failed_key_never_retries_and_new_explicit_key_can_run(api_app, api_catalog):
    class Failing(CountingProvider):
        def generate(self, context):
            self.calls += 1
            raise AIProviderError("Failure from fake provider")

    with api_app.app_context():
        provider = Failing()
        service = Service(api_app.config, provider)
        request = data(api_catalog, request_key=secrets.token_urlsafe(32))
        with pytest.raises(AIProviderError):
            service.create_session(**request)
        with pytest.raises(WorkflowConflictError, match="failed"):
            service.create_session(**request)
        assert provider.calls == 1
        assert GenerationRun.query.one().active_request_scope is None
        with pytest.raises(AIProviderError):
            service.create_session(**{**request, "request_key": secrets.token_urlsafe(32)})
        assert provider.calls == GenerationRun.query.count() == 2
        assert Design.query.count() == Draft.query.count() == 0


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_submissions_only_dispatch_once(api_app, api_catalog, same_key):
    barrier = threading.Barrier(2)
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = []
    sessions = []
    key = secrets.token_urlsafe(32)

    class Blocking(MockTestDesignProvider):
        def generate(self, context):
            with lock:
                calls.append(1)
            entered.set()
            assert release.wait(10), "test did not release the fake provider"
            return super().generate(context)

    def submit(token):
        with api_app.app_context():
            with lock:
                sessions.append(db.session())
            barrier.wait(timeout=5)
            try:
                result = Service(api_app.config, Blocking()).create_session(
                    **data(api_catalog, request_key=token),
                )
                return ("success", result.id)
            except WorkflowConflictError as exc:
                return ("conflict", exc.details)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, key), executor.submit(
            submit, key if same_key else secrets.token_urlsafe(32),
        )]
        try:
            assert entered.wait(5)
            done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
            assert len(done) == 1
            assert next(iter(done)).result()[0] == "conflict"
        finally:
            release.set()
        outcomes = [future.result(timeout=5) for future in futures]
    assert len({id(session) for session in sessions}) == 2
    assert sorted(outcome[0] for outcome in outcomes) == ["conflict", "success"]
    assert len(calls) == 1
    with api_app.app_context():
        assert GenerationRun.query.count() == Design.query.count() == 1
        assert Draft.query.count() == 3


def test_legacy_no_key_preserves_independent_attempts(api_app, api_catalog):
    with api_app.app_context():
        provider = CountingProvider()
        service = Service(api_app.config, provider)
        first = service.create_session(**data(api_catalog))
        second = service.create_session(**data(api_catalog))
        assert first.id != second.id
        assert provider.calls == GenerationRun.query.count() == 2
        assert all(run.request_key is None and run.active_request_scope is None
                   for run in GenerationRun.query.all())


def test_invalid_configuration_cannot_silently_succeed_as_mock(api_app, api_catalog):
    from config import load_runtime_ai_config

    broken = load_runtime_ai_config({"AI_PROVIDER": "deepseek", "AI_REQUEST_TIMEOUT_SECONDS": "bad"})
    assert broken["AI_PROVIDER"] == "mock" and broken["AI_CONFIG_ERROR"]
    with api_app.app_context():
        with pytest.raises(AIConfigurationError, match="invalid"):
            Service(broken).create_session(**data(api_catalog))
        assert GenerationRun.query.count() == Design.query.count() == 0


def test_web_requires_submission_key_before_provider_call(api_client, api_catalog):
    response = api_client.post("/ai-test-design/new", data=data(api_catalog))
    assert "Invalid submission key" in response.get_data(as_text=True)
    with api_client.application.app_context():
        assert GenerationRun.query.count() == 0


def test_additive_migration_matches_current_models(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}"})
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        indexes = {item["name"]: item for item in inspect(db.engine).get_indexes("generation_run")}
        assert indexes["uq_generation_run_request_key"]["unique"]
        assert indexes["uq_generation_run_active_scope"]["unique"]
    result = runner.invoke(args=["db", "check"])
    assert result.exit_code == 0, result.output


def test_competing_run_finishes_before_conflict_lookup_retains_result_link(api_app, api_catalog, monkeypatch):
    from app.services.test_design.evidence import GenerationRecorder
    from app.services.test_design.schemas import TestDesignContext as Context
    from app.services.test_design.submissions import submission_fingerprint

    with api_app.app_context():
        request = data(api_catalog)
        provider = CountingProvider()
        context = Context(title=request["title"], requirement_text=request["requirement_text"])
        fingerprint = submission_fingerprint(context, request["project_id"], request["version_id"], provider)
        recorder = GenerationRecorder(api_app.config)
        run_id = recorder.start(context=context, project_id=request["project_id"],
                                version_id=request["version_id"], provider=provider,
                                request_key=secrets.token_urlsafe(32), request_fingerprint=fingerprint)
        original = GenerationRecorder._resolve_submission_conflict

        def finish_before_lookup(self, key, value):
            recorder.fail(run_id, error=AIProviderError("demo failure"), metadata={}, latency_ms=1)
            return original(self, key, value)

        monkeypatch.setattr(GenerationRecorder, "_resolve_submission_conflict", finish_before_lookup)
        with pytest.raises(WorkflowConflictError, match="changed state") as conflict:
            Service(api_app.config, provider).create_session(**request, request_key=secrets.token_urlsafe(32))
        assert conflict.value.details == {"run_id": run_id, "run_status": "failed"}
        assert provider.calls == 0
        assert GenerationRun.query.count() == 1
