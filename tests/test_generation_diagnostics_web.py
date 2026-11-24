import json
import secrets
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import GenerationRun, TestCaseDraft as Draft, TestDesignSession as Design
from app.services.ai.exceptions import AIProviderError, AIResponseError
from app.services.test_design.deepseek_provider import DeepSeekTestDesignProvider
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design_service import TestDesignService as Service
from app.services.workflow_errors import WorkflowPersistenceError


def data(catalog):
    return dict(project_id=catalog["first_project_id"], version_id=catalog["first_version_id"],
                title="Demo diagnostics", requirement_text="Sample audio requirement with a mock volume slider.",
                request_key=secrets.token_urlsafe(32))


def fake_deepseek(*, content=None, timeout=False):
    def create(**kwargs):
        if timeout:
            raise APITimeoutError(request=httpx.Request("POST", "https://example.test"))
        return SimpleNamespace(model="demo-model", usage=None, choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=content),
        )])

    return DeepSeekTestDesignProvider(
        api_key="demo-test-key", model="demo-model", base_url="https://example.test",
        timeout_seconds=1, max_output_tokens=2000,
        client_factory=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )),
    )


@pytest.mark.parametrize("timeout,category", [(False, "missing_field"), (True, "api_timeout")])
def test_failure_diagnostics_persist_without_raw_body(api_app, api_catalog, timeout, category):
    with api_app.app_context():
        provider = fake_deepseek(content='{"unexpected_secret_field":"do-not-retain-body"}', timeout=timeout)
        with pytest.raises((AIProviderError, AIResponseError)):
            Service(api_app.config, provider).create_session(**data(api_catalog))
        run = GenerationRun.query.one()
        summary = json.loads(run.validation_summary_json)
        assert category in summary["error_categories"]
        assert "do-not-retain-body" not in run.validation_summary_json
        assert "unexpected_secret_field" not in run.validation_summary_json
        assert run.status == "failed" and run.active_request_scope is None
        assert run.structured_output_json is None
        assert Draft.query.count() == Design.query.count() == 0


def test_business_persistence_failure_keeps_diagnostic_and_no_partial_rows(api_app, api_catalog, monkeypatch):
    with api_app.app_context():
        session = db.session()
        original = session.commit

        def fail_business_commit():
            raise SQLAlchemyError("private database detail")

        monkeypatch.setattr(session, "commit", fail_business_commit)
        with pytest.raises(WorkflowPersistenceError):
            Service(api_app.config, MockTestDesignProvider()).create_session(**data(api_catalog))
        monkeypatch.setattr(session, "commit", original)
        run = GenerationRun.query.one()
        assert json.loads(run.validation_summary_json)["stage"] == "business_persistence"
        assert run.status == "failed" and run.active_request_scope is None
        assert "private database detail" not in run.error_message
        assert Design.query.count() == Draft.query.count() == 0
        assert run.structured_output_json is not None


def test_failed_run_view_passes_only_sanitized_diagnostics(api_app, api_catalog, monkeypatch):
    with api_app.app_context():
        with pytest.raises(AIResponseError):
            Service(api_app.config, fake_deepseek(content="{}")).create_session(**data(api_catalog))
        run_id = GenerationRun.query.one().id
    captured = {}

    def render(template, **context):
        captured.update(template=template, **context)
        return "safe run page"

    monkeypatch.setattr("app.blueprints.ai_test_design.routes.render_template", render)
    response = api_app.test_client().get(f"/ai-test-design/runs/{run_id}")
    assert response.status_code == 200
    assert captured["template"] == "ai_test_design/run.html"
    assert captured["validation_summary"]["stage"] == "schema"
    assert captured["run"].status == "failed"
