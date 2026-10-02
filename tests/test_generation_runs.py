import hashlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from test_design_contract import PROMPT_VERSION

from app import create_app
from app.extensions import db
from app.models import Project, TestCaseDraft as Draft, TestDesignSession as Design, Version
from app.services.ai.exceptions import AIProviderError, AIResponseError
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design_service import TestDesignService as DesignService
from app.services.workflow_errors import WorkflowPersistenceError


@pytest.fixture()
def catalog(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'runs.sqlite').as_posix()}",
        "AI_PROVIDER": "mock", "AI_ENABLED": False,
        "DEEPSEEK_API_KEY": "configured-private-value", "SECRET_KEY": "another-private-value",
    })
    with app.app_context():
        db.create_all()
        project = Project(name="Demo project", code="DEMO-RUNS")
        db.session.add(project)
        db.session.flush()
        version = Version(project_id=project.id, name="Demo version", code="DEMO-V1")
        db.session.add(version)
        db.session.commit()
        yield app, {"project_id": project.id, "version_id": version.id,
                    "title": "Demo login API", "requirement_text":
                    "Demo login API: require username and password; lock after five failures."}
        db.session.remove()
        db.drop_all()


def runs():
    from app.models import GenerationRun
    return GenerationRun.query.order_by(GenerationRun.id).all()


def test_mock_success_persists_source_snapshot_hashes_and_null_usage(catalog):
    app, data = catalog
    session = DesignService(app.config).create_session(**data)
    run = runs()[0]
    assert run.session_id == session.id
    assert run.status == "succeeded" and run.provider == "mock"
    assert run.requirement_hash == hashlib.sha256(data["requirement_text"].encode()).hexdigest()
    assert len(run.prompt_hash) == 64 and run.prompt_version == session.prompt_version == PROMPT_VERSION
    assert run.started_at <= run.finished_at and run.latency_ms >= 0
    assert run.input_chars > len(data["requirement_text"]) and run.output_chars > 0
    assert (run.prompt_tokens, run.completion_tokens, run.total_tokens, run.finish_reason) == (None,) * 4
    assert all(d.generation_run_id == run.id for d in session.drafts)
    assert len(json.loads(run.structured_output_json)["case_drafts"]) == len(session.drafts)


@pytest.mark.parametrize("failure", ["sdk", "schema", "authorization", "configured_secret"])
def test_failed_calls_keep_evidence_without_partial_business_records(catalog, failure):
    app, data = catalog
    class Provider:
        provider_name = "deepseek"
        provider_model = "demo-model"
        def generate(self, context):
            self.last_call_metadata = SimpleNamespace(prompt_tokens=13, completion_tokens=8,
                                                     total_tokens=21, finish_reason="stop", output_chars=50)
            if failure == "sdk":
                raise RuntimeError("Authorization: Bearer unprefixed-value " + app.config["DEEPSEEK_API_KEY"])
            if failure == "schema":
                return {"summary": "invalid"}
            result = MockTestDesignProvider().generate(context).model_dump(mode="json")
            result["summary"] = "Demo Authorization: Bearer arbitrary-sensitive-value" if failure == "authorization" else "Demo " + app.config["SECRET_KEY"]
            return result
    with pytest.raises((AIProviderError, AIResponseError)):
        DesignService(app.config, Provider()).create_session(**data)
    run = runs()[0]
    assert run.status == "failed" and run.session_id is None
    assert run.requirement_text == data["requirement_text"]
    assert run.structured_output_json is None
    assert run.latency_ms >= 0 and run.finished_at is not None
    assert run.total_tokens == 21
    assert all(secret not in run.error_message for secret in
               (app.config["DEEPSEEK_API_KEY"], app.config["SECRET_KEY"], "arbitrary-sensitive-value", "unprefixed-value"))
    assert Design.query.count() == Draft.query.count() == 0


def test_business_commit_failure_preserves_failed_run_and_validated_snapshot(catalog, monkeypatch):
    app, data = catalog
    def fail_commit():
        db.session.flush()
        raise OperationalError("private statement", {}, Exception("configured-private-value"))
    monkeypatch.setattr(db.session(), "commit", fail_commit)
    with pytest.raises(WorkflowPersistenceError):
        DesignService(app.config).create_session(**data)
    run = runs()[0]
    assert run.status == "failed" and run.session_id is None
    assert run.error_type == "WorkflowPersistenceError"
    assert run.structured_output_json is not None
    assert Design.query.count() == Draft.query.count() == 0


def test_run_must_be_durable_before_provider_call(catalog, monkeypatch):
    from app.services.test_design.evidence import GenerationRecorder
    app, data = catalog
    provider = MockTestDesignProvider()
    called = []
    monkeypatch.setattr(provider, "generate", lambda _context: called.append(True))
    monkeypatch.setattr(GenerationRecorder, "start", lambda *a, **kw: (_ for _ in ()).throw(WorkflowPersistenceError("Cannot record call.")))
    with pytest.raises(WorkflowPersistenceError):
        DesignService(app.config, provider).create_session(**data)
    assert called == [] and runs() == []


def test_same_session_multiple_runs_keep_draft_provenance_and_original_snapshot(catalog):
    app, data = catalog
    service = DesignService(app.config)
    session = service.create_session(**data)
    original_ids = [d.id for d in session.drafts]
    first_snapshot = runs()[0].structured_output_json
    service.generate_for_session(session.id)
    assert len(runs()) == 2 and all(r.session_id == session.id for r in runs())
    assert [d.id for d in session.drafts][:len(original_ids)] == original_ids
    assert len(session.drafts) == len(original_ids) * 2
    assert runs()[0].structured_output_json == first_snapshot
    assert {d.generation_run_id for d in session.drafts} == {r.id for r in runs()}


def test_session_with_many_runs_preserves_history_and_can_still_be_scored(catalog):
    app, data = catalog
    service = DesignService(app.config)
    session = service.create_session(**data)
    for _ in range(6):
        service.generate_for_session(session.id)
    assert len(session.drafts) == 21
    assert len(service.session_result(session).case_drafts) == 21
    assert session.quality_score == service.assessment_for_session(session).quality_score


def test_retry_stored_quality_matches_preserved_draft_collection(catalog):
    app, data = catalog
    session = DesignService(app.config).create_session(**data)
    class NormalOnly(MockTestDesignProvider):
        def generate(self, context):
            payload = super().generate(context).model_dump(mode="json")
            payload["case_drafts"] = payload["case_drafts"][:1]
            return payload
    service = DesignService(app.config, NormalOnly())
    service.generate_for_session(session.id)
    assert session.quality_score == service.assessment_for_session(session).quality_score == 100


def test_retry_failure_keeps_existing_session_drafts(catalog):
    app, data = catalog
    session = DesignService(app.config).create_session(**data)
    original = [d.id for d in session.drafts]
    class BadProvider:
        provider_name = "mock"
        provider_model = None
        def generate(self, _context):
            raise AIProviderError("SECRET_KEY=another-private-value")
    with pytest.raises(AIProviderError) as caught:
        DesignService(app.config, BadProvider()).generate_for_session(session.id)
    assert "another-private-value" not in str(caught.value)
    assert [d.id for d in session.drafts] == original
    assert runs()[-1].session_id == session.id and runs()[-1].status == "failed"


def test_provider_model_and_finish_reason_cannot_persist_secrets(catalog):
    app, data = catalog
    class Provider(MockTestDesignProvider):
        provider_name = "deepseek"
        provider_model = "demo-model"
        def generate(self, context):
            result = super().generate(context)
            self.last_call_metadata = SimpleNamespace(provider_model=app.config["DEEPSEEK_API_KEY"], finish_reason="Authorization: Bearer private", prompt_tokens=-1, total_tokens=True)
            return result
    session = DesignService(app.config, Provider()).create_session(**data)
    assert runs()[0].provider_model == session.provider_model == "demo-model"
    assert runs()[0].finish_reason is None
    assert runs()[0].prompt_tokens is None and runs()[0].total_tokens is None


def test_malformed_huge_temperature_does_not_lose_call_evidence(catalog):
    app, data = catalog
    class Provider(MockTestDesignProvider):
        def generate(self, context):
            result = super().generate(context)
            self.last_call_metadata = SimpleNamespace(temperature=10**1000)
            return result
    DesignService(app.config, Provider()).create_session(**data)
    assert runs()[0].status == "succeeded" and runs()[0].temperature is None


def test_concurrent_finalization_cannot_overwrite_terminal_evidence(catalog):
    from app.models import GenerationRun
    from app.services.test_design.evidence import GenerationRecorder
    from app.services.test_design.schemas import TestDesignContext as Context
    app, data = catalog
    context = Context(title=data["title"], requirement_text=data["requirement_text"])
    run_id = GenerationRecorder(app.config).start(
        context=context, project_id=data["project_id"], version_id=data["version_id"],
        provider=MockTestDesignProvider(),
    )
    won = []
    def concurrent_write(_mapper, _connection, _target):
        # Interleave after the terminal guard SELECT and before the UPDATE.
        if won:
            return
        won.append(True)
        with Session(bind=db.engine) as second:
            record = second.get(GenerationRun, run_id)
            record.status = "failed"
            record.error_message = "The earlier writer finalized failure."
            second.commit()
    event.listen(GenerationRun, "before_update", concurrent_write)
    try:
        with Session(bind=db.engine) as first:
            record = first.get(GenerationRun, run_id)
            record.status = "succeeded"
            with pytest.raises(StaleDataError):
                first.commit()
            first.rollback()
    finally:
        event.remove(GenerationRun, "before_update", concurrent_write)
    assert runs()[0].status == "failed"
    assert runs()[0].error_message == "The earlier writer finalized failure."


@pytest.mark.parametrize("usage", [None, SimpleNamespace(prompt_tokens=22, completion_tokens=11, total_tokens=33)])
def test_deepseek_fakeclient_metadata_reaches_persisted_run(catalog, usage):
    from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider
    from app.services.test_design.schemas import TestDesignContext as Context
    app, data = catalog
    payload = MockTestDesignProvider().generate(Context(
        title=data["title"], requirement_text=data["requirement_text"],
    )).model_dump(mode="json")
    response = SimpleNamespace(model="deepseek-response-model", usage=usage,
                               choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(payload)))])
    provider = DeepSeekTestDesignProvider(
        api_key="configured-private-value", model="deepseek-configured-model",
        base_url="https://api.deepseek.com", timeout_seconds=5, max_output_tokens=1800,
        client_factory=lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))),
    )
    session = DesignService(app.config, provider).create_session(**data)
    run = runs()[0]
    assert run.provider == "deepseek" and run.status == "succeeded"
    assert run.provider_model == session.provider_model == "deepseek-response-model"
    assert run.finish_reason == "stop" and run.max_tokens == 1800 and run.temperature is None
    assert (run.prompt_tokens, run.completion_tokens, run.total_tokens) == ((22, 11, 33) if usage else (None, None, None))
    assert run.output_chars == len(response.choices[0].message.content)
