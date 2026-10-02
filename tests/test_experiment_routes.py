import json
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    GenerationRun,
    Project,
    ReviewRecord,
    TestCase as ModelTestCase,
    TestCaseDraft as ModelTestCaseDraft,
    User,
    Version,
)
from app.services.test_design_service import TestDesignService as DesignService


@pytest.fixture()
def experiment_app(tmp_path):
    database_path = tmp_path / "experiment_routes.sqlite"
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "AI_ENABLED": False,
            "AI_PROVIDER": "mock",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_MODEL": "",
        }
    )
    with application.app_context():
        db.create_all()
        project = Project(name="Demo evidence project", code="DEMO-EVIDENCE")
        db.session.add(project)
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo evidence version",
            code="FW_DEMO_EVIDENCE",
        )
        reviewer = User(username="Demo reviewer", email="reviewer@example.test")
        reviewer.set_password("demo-review-password")
        other = User(username="Other reviewer", email="other@example.test")
        other.set_password("other-review-password")
        db.session.add_all((version, reviewer, other))
        db.session.commit()
        session = DesignService(application.config).create_session(
            project_id=project.id,
            version_id=version.id,
            title="Demo evidence route design",
            requirement_text="Sample audio volume control for a mock connected device.",
        )
        application.config["EVIDENCE_TEST_IDS"] = {
            "session": session.id,
            "draft": session.drafts[0].id,
            "reviewer": reviewer.id,
            "other": other.id,
            "project": project.id,
            "version": version.id,
        }
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def anonymous_client(experiment_app):
    return experiment_app.test_client()


@pytest.fixture()
def reviewer_client(experiment_app):
    client = experiment_app.test_client()
    response = client.post(
        "/auth/login",
        data={
            "email": "reviewer@example.test",
            "password": "demo-review-password",
        },
    )
    assert response.status_code == 302
    return client


def _draft_form(draft, **overrides):
    data = {
        field: getattr(draft, field) or ""
        for field in (
            "suggested_code", "title", "module", "priority", "case_type",
            "scenario_type", "precondition", "steps", "expected_result",
        )
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    ("method", "action"),
    [("get", "edit"), ("post", "edit"), ("post", "accept"), ("post", "reject")],
)
def test_anonymous_review_routes_redirect_before_service_and_do_not_mutate(
    experiment_app, anonymous_client, monkeypatch, method, action,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    calls = []

    def unauthorized_review(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(id=999)

    service_method = "update_draft" if action == "edit" else f"{action}_draft"
    monkeypatch.setattr(DesignService, service_method, unauthorized_review)
    with experiment_app.app_context():
        draft = db.session.get(ModelTestCaseDraft, ids["draft"])
        data = _draft_form(draft, title="Unauthorized title mutation")
        original_title = draft.title
    response = getattr(anonymous_client, method)(
        f"/ai-test-design/drafts/{ids['draft']}/{action}", data=data,
    )

    assert response.status_code == 302
    assert "/auth/login?next=" in response.headers["Location"]
    assert calls == []
    with experiment_app.app_context():
        draft = db.session.get(ModelTestCaseDraft, ids["draft"])
        assert draft.title == original_title
        assert draft.status == "pending"
        assert draft.accepted_test_case_id is None
        assert ModelTestCase.query.count() == 0
        assert ReviewRecord.query.count() == 0


def test_logged_in_edit_records_identity_and_separate_comment(
    experiment_app, reviewer_client,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    with experiment_app.app_context():
        data = _draft_form(
            db.session.get(ModelTestCaseDraft, ids["draft"]),
            title="Demo human edited title",
            comment="Checked the sample requirement.",
        )
    response = reviewer_client.post(
        f"/ai-test-design/drafts/{ids['draft']}/edit", data=data,
    )

    assert response.status_code == 302
    with experiment_app.app_context():
        record = ReviewRecord.query.one()
        assert record.reviewer_user_id == ids["reviewer"]
        assert record.action == "edit"
        assert record.comment == "Checked the sample requirement."
        assert json.loads(record.changed_fields_json) == ["title"]
        assert record.changed_field_count == 1


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_review_action_ignores_forged_identity_and_uses_signed_in_user(
    experiment_app, reviewer_client, action,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    response = reviewer_client.post(
        f"/ai-test-design/drafts/{ids['draft']}/{action}",
        data={"reviewer_user_id": ids["other"], "comment": "Sample review complete."},
    )

    assert response.status_code == 302
    with experiment_app.app_context():
        record = ReviewRecord.query.one()
        assert record.reviewer_user_id == ids["reviewer"]
        assert record.action == action
        assert record.comment == "Sample review complete."
        assert record.changed_field_count == 0


def test_edit_rejects_forged_reviewer_as_unknown_field(
    experiment_app, reviewer_client,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    with experiment_app.app_context():
        data = _draft_form(
            db.session.get(ModelTestCaseDraft, ids["draft"]),
            reviewer_user_id=str(ids["other"]),
        )
    response = reviewer_client.post(
        f"/ai-test-design/drafts/{ids['draft']}/edit", data=data,
    )

    assert response.status_code == 200
    assert "Unknown form field: reviewer_user_id" in response.get_data(as_text=True)
    with experiment_app.app_context():
        assert ReviewRecord.query.count() == 0


@pytest.mark.parametrize("action", ["edit", "accept", "reject"])
@pytest.mark.parametrize(
    ("comment", "message"),
    [("x" * 1001, "1000 characters"),
     ("Authorization: Bearer demo-secret-value", "forbidden sensitive content")],
)
def test_review_comment_validation_is_safe_and_preserves_pending_draft(
    experiment_app, reviewer_client, action, comment, message,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    data = {"comment": comment}
    if action == "edit":
        with experiment_app.app_context():
            data.update(_draft_form(db.session.get(ModelTestCaseDraft, ids["draft"])))
    response = reviewer_client.post(
        f"/ai-test-design/drafts/{ids['draft']}/{action}",
        data=data,
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert message in page
    assert "demo-secret-value" not in page
    with experiment_app.app_context():
        assert db.session.get(ModelTestCaseDraft, ids["draft"]).status == "pending"
        assert ReviewRecord.query.count() == 0
        assert ModelTestCase.query.count() == 0


def test_detail_displays_generation_review_history_and_rule_metrics(
    experiment_app, reviewer_client,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    with experiment_app.app_context():
        data = _draft_form(
            db.session.get(ModelTestCaseDraft, ids["draft"]),
            title="Demo reviewed evidence title",
            comment="<script>sample review</script>",
        )
    reviewer_client.post(f"/ai-test-design/drafts/{ids['draft']}/edit", data=data)
    reviewer_client.post(
        f"/ai-test-design/drafts/{ids['draft']}/accept",
        data={"comment": "Sample accepted after checking."},
    )
    page = reviewer_client.get(
        f"/ai-test-design/{ids['session']}"
    ).get_data(as_text=True)

    for value in (
        "Generation history", "test-design-v2", "succeeded", "Not returned",
        "Prompt tokens", "Completion tokens", "Total tokens", "Finish reason",
        "Latency", "UTC", "Review history", "Demo reviewer", "edit", "accept",
        "Changed fields", "title", "Rule-based session quality",
        "Human review metrics", "Edited drafts", "Average changed fields",
        "Sample accepted after checking.", "&lt;script&gt;sample review&lt;/script&gt;",
    ):
        assert value in page
    assert "<script>sample review</script>" not in page
    assert "You are a constrained test design assistant" not in page


def test_anonymous_detail_explains_sign_in_requirement(experiment_app, anonymous_client):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    page = anonymous_client.get(
        f"/ai-test-design/{ids['session']}"
    ).get_data(as_text=True)

    assert "Sign in to edit, accept, or reject drafts" in page
    assert 'action="/ai-test-design/drafts/' not in page


def test_list_displays_orphan_runs_and_applies_project_version_provider_filters(
    experiment_app, anonymous_client,
):
    ids = experiment_app.config["EVIDENCE_TEST_IDS"]
    with experiment_app.app_context():
        project = Project(name="Sample other evidence project", code="OTHER-EVIDENCE")
        db.session.add(project)
        db.session.flush()
        version = Version(
            project_id=project.id, name="Other version", code="FW_OTHER_EVIDENCE",
        )
        db.session.add(version)
        db.session.flush()
        common = {
            "requirement_text": "Sample mock input.",
            "prompt_version": "test-design-v1",
            "prompt_hash": "a" * 64,
            "requirement_hash": "b" * 64,
        }
        db.session.add_all((
            GenerationRun(
                **common, title="Demo safe failed call", project_id=ids["project"],
                version_id=ids["version"], provider="mock", status="failed",
                error_type="AIProviderError", error_message="Safe provider failure.",
            ),
            GenerationRun(
                **common, title="Demo still running call", project_id=ids["project"],
                version_id=ids["version"], provider="mock", status="running",
            ),
            GenerationRun(
                **common, title="Other project failed call", project_id=project.id,
                version_id=version.id, provider="deepseek", status="failed",
            ),
        ))
        db.session.commit()
    response = anonymous_client.get(
        "/ai-test-design/",
        query_string={
            "project_id": ids["project"], "version_id": ids["version"],
            "provider": "mock",
        },
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Calls without a design session" in page
    assert "Demo safe failed call" in page
    assert "Demo still running call" in page
    assert "Safe provider failure." in page
    assert "Other project failed call" not in page
    assert "UTC" in page
