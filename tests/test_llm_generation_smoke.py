import json
from types import SimpleNamespace

from app.extensions import db
from app.models import GenerationRun, TestCaseDraft as Draft, TestDesignSession as Design
from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design.prompts import PROMPT_VERSION, prompt_hash, requirement_hash
from app.services.test_design.schemas import TestDesignContext as Context
from app.services.test_design_service import TestDesignService as Service
from scripts.llm_generation_smoke import DEMO_REQUIREMENT, execute_smoke


def install_fake_client(monkeypatch, app, *, truncated=False, during_call=None):
    captured = {"calls": []}
    payload = MockTestDesignProvider().generate(Context(
        title="Demo login API thesis smoke", requirement_text=DEMO_REQUIREMENT,
    )).model_dump(mode="json")

    def create(**kwargs):
        captured["calls"].append(kwargs)
        if during_call:
            during_call()
        return SimpleNamespace(
            model="deepseek-response-model",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300),
            choices=[SimpleNamespace(
                finish_reason="length" if truncated else "stop",
                message=SimpleNamespace(content=json.dumps(payload)),
            )],
        )

    def factory(**kwargs):
        captured["client_options"] = kwargs
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def provider(service):
        captured["service_config"] = dict(service.config)
        return DeepSeekTestDesignProvider(
            api_key=service.config["DEEPSEEK_API_KEY"],
            model=service.config["DEEPSEEK_MODEL"],
            base_url=service.config["DEEPSEEK_BASE_URL"],
            timeout_seconds=service.config["AI_REQUEST_TIMEOUT_SECONDS"],
            max_output_tokens=service.config["AI_MAX_OUTPUT_TOKENS"],
            client_factory=factory,
        )

    app.config.update(DEEPSEEK_API_KEY="arbitrary-secret-value",
                      DEEPSEEK_MODEL="deepseek-configured-model",
                      AI_MAX_OUTPUT_TOKENS=2000, AI_REQUEST_TIMEOUT_SECONDS=20)
    monkeypatch.setattr(Service, "_create_provider", provider)
    return captured


def call_smoke(app, catalog):
    return execute_smoke(app, project_id=catalog["first_project_id"],
                         version_id=catalog["first_version_id"], execute=True)


def test_smoke_without_credentials_is_pending_and_never_calls_provider(api_app, monkeypatch):
    def forbid_call(*args, **kwargs):
        raise AssertionError("A pending smoke must not call a model.")
    from app.services.test_design_service import TestDesignService
    monkeypatch.setattr(TestDesignService, "create_session", forbid_call)
    api_app.config["DEEPSEEK_API_KEY"] = ""
    report = execute_smoke(api_app, project_id=1, version_id=1, execute=True)
    assert report["executed"] is False
    assert report["result"] == "pending: missing valid API credential"


def test_smoke_requires_explicit_execution_even_with_credential(api_app, monkeypatch):
    def forbid_call(*args, **kwargs):
        raise AssertionError("An unrequested smoke must not call a model.")
    from app.services.test_design_service import TestDesignService
    monkeypatch.setattr(TestDesignService, "create_session", forbid_call)
    api_app.config["DEEPSEEK_API_KEY"] = "arbitrary-secret-value"
    report = execute_smoke(api_app, project_id=1, version_id=1)
    assert report["executed"] is False and report["token_usage"] is None
    assert "arbitrary-secret-value" not in str(report)


def test_smoke_succeeds_only_with_persisted_call_session_and_draft_sources(
    api_app, api_catalog, monkeypatch,
):
    captured = install_fake_client(monkeypatch, api_app)
    report = call_smoke(api_app, api_catalog)

    assert captured["service_config"]["AI_MAX_OUTPUT_TOKENS"] == 8000
    assert captured["client_options"]["timeout"] == 60
    assert captured["client_options"]["max_retries"] == 0
    assert len(captured["calls"]) == 1
    assert api_app.config["AI_MAX_OUTPUT_TOKENS"] == 2000
    assert api_app.config["AI_REQUEST_TIMEOUT_SECONDS"] == 20
    assert report["result"] == "succeeded" and report["closed_loop_validated"] is True
    assert report["requested_model"] == "deepseek-configured-model"
    assert report["model"] == "deepseek-response-model"
    assert report["max_tokens"] == 8000 and report["finish_reason"] == "stop"
    assert report["schema_validation"] is True and report["draft_sources_valid"] is True
    assert report["session_persisted"] is True and report["drafts_persisted"] is True
    assert report["input_chars"] > len(DEMO_REQUIREMENT) and report["output_chars"] > 0
    assert report["prompt_hash"] == prompt_hash()
    assert report["requirement_hash"] == requirement_hash(DEMO_REQUIREMENT)
    assert "arbitrary-secret-value" not in json.dumps(report)
    with api_app.app_context():
        run = db.session.get(GenerationRun, report["run_id"])
        session = db.session.get(Design, report["session_id"])
        assert run.status == "succeeded" and run.session_id == session.id
        assert run.prompt_version == session.prompt_version == PROMPT_VERSION
        assert report["draft_count"] == len(session.drafts) > 0
        assert report["test_point_count"] == len(json.loads(session.test_points_json)) > 0
        assert all(d.status == "pending" and d.generation_run_id == run.id for d in session.drafts)


def test_smoke_truncation_keeps_failed_evidence_and_no_business_records(
    api_app, api_catalog, monkeypatch,
):
    captured = install_fake_client(monkeypatch, api_app, truncated=True)
    report = call_smoke(api_app, api_catalog)

    assert len(captured["calls"]) == 1
    assert report["result"] == "failed" and report["closed_loop_validated"] is False
    assert report["status"] == "failed" and report["finish_reason"] == "length"
    assert report["schema_validation"] is False
    assert report["generation_run_persisted"] is True
    assert "arbitrary-secret-value" not in json.dumps(report)
    with api_app.app_context():
        assert GenerationRun.query.count() == 1
        assert Design.query.count() == Draft.query.count() == 0


def test_smoke_ignores_a_concurrent_unrelated_run(api_app, api_catalog, monkeypatch):
    def other_generation():
        Service(api_app.config, provider=MockTestDesignProvider()).create_session(
            project_id=api_catalog["second_project_id"],
            version_id=api_catalog["other_version_id"],
            title="Other Demo requirement",
            requirement_text="Sample audio requirement for an unrelated mock call.",
        )

    captured = install_fake_client(monkeypatch, api_app, during_call=other_generation)
    report = call_smoke(api_app, api_catalog)

    assert len(captured["calls"]) == 1
    assert report["model"] == "deepseek-response-model"
    assert report["result"] == "succeeded" and report["closed_loop_validated"] is True
    with api_app.app_context():
        assert GenerationRun.query.count() == 2
        assert db.session.get(GenerationRun, report["run_id"]).session_id == report["session_id"]


def test_returned_object_without_persisted_evidence_cannot_pass_smoke(
    api_app, api_catalog, monkeypatch,
):
    api_app.config["DEEPSEEK_API_KEY"] = "arbitrary-secret-value"
    monkeypatch.setattr(Service, "create_session", lambda *args, **kwargs: SimpleNamespace(
        id=999, test_points_json='[{}]', drafts=[SimpleNamespace(id=999)],
    ))

    report = call_smoke(api_app, api_catalog)

    assert report["result"] == "failed"
    assert report["closed_loop_validated"] is False
    assert report["generation_run_persisted"] is False


def test_smoke_cannot_pass_with_draft_from_another_run(api_app, api_catalog, monkeypatch):
    install_fake_client(monkeypatch, api_app)
    create_session = Service.create_session

    def incorrect_provenance(service, **kwargs):
        unrelated = Service(api_app.config, provider=MockTestDesignProvider())._generate(
            Context(title="Other demo", requirement_text="Sample mock requirement for another call."),
            api_catalog["first_project_id"], api_catalog["first_version_id"],
            MockTestDesignProvider(),
        )
        wrong_run_id = unrelated.drafts[0].generation_run_id
        session = create_session(service, **kwargs)
        session.drafts[0].generation_run_id = wrong_run_id
        db.session.commit()
        return session

    monkeypatch.setattr(Service, "create_session", incorrect_provenance)
    report = call_smoke(api_app, api_catalog)

    assert report["result"] == "failed" and report["closed_loop_validated"] is False
    assert report["schema_validation"] is True and report["drafts_persisted"] is True
    assert report["draft_sources_valid"] is False
