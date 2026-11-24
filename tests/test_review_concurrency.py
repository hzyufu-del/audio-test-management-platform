import pytest

from app.extensions import db
from app.models import ReviewRecord, TestCase as Case, TestCaseDraft as Draft, TestDesignSession as Design, User
from app.services.test_design.schemas import DraftEditInput
from app.services.test_design_service import TestDesignService as Service
from app.services.workflow_errors import WorkflowConflictError


@pytest.fixture()
def review_catalog(api_app, api_catalog):
    with api_app.app_context():
        user = User(username="Demo concurrent reviewer", email="concurrent@example.test")
        user.set_password("demo-password")
        db.session.add(user)
        db.session.commit()
        session = Service(api_app.config).create_session(
            project_id=api_catalog["first_project_id"], version_id=api_catalog["first_version_id"],
            title="Demo concurrent review", requirement_text="Sample mock volume control with visible bounded values.",
        )
        yield {"user": user.id, "session": session.id, "drafts": [d.id for d in session.drafts], "initial_case_count":Case.query.count()}


def payload(draft):
    result = {field:getattr(draft, field) for field in DraftEditInput.model_fields}
    result["precondition"] = result["precondition"] or ""
    result["title"] = "Demo concurrent revised title"
    return result


def test_stale_session_edit_after_another_accept_rolls_back(api_app, review_catalog):
    ids = review_catalog
    with api_app.app_context():
        old = db.session.get(Draft, ids["drafts"][0])
        values = payload(old)
        # Force the same old aggregate snapshot that a review page can hold.
        list(old.session.drafts)
        with api_app.app_context():
            accepted = Service(api_app.config).accept_draft(old.id, reviewer_user_id=ids["user"])
            case_id = accepted.id
        with pytest.raises(WorkflowConflictError, match="changed"):
            Service(api_app.config).update_draft(old.id, values, reviewer_user_id=ids["user"])
    with api_app.app_context():
        draft = db.session.get(Draft, ids["drafts"][0])
        assert draft.status == "accepted"
        assert draft.title == db.session.get(Case, case_id).title
        assert [r.action for r in draft.review_records] == ["accept"]


def test_stale_different_draft_review_cannot_lose_aggregate_state(api_app, review_catalog):
    ids = review_catalog
    # Leave just two pending drafts so a stale aggregate would be observable.
    with api_app.app_context():
        for did in ids["drafts"][2:]:
            Service(api_app.config).reject_draft(did, reviewer_user_id=ids["user"])
    with api_app.app_context():
        old = db.session.get(Draft, ids["drafts"][1])
        list(old.session.drafts)
        with api_app.app_context():
            Service(api_app.config).reject_draft(ids["drafts"][0], reviewer_user_id=ids["user"])
        with pytest.raises(WorkflowConflictError, match="changed"):
            Service(api_app.config).reject_draft(old.id, reviewer_user_id=ids["user"])
    with api_app.app_context():
        assert db.session.get(Draft, ids["drafts"][1]).status == "pending"
        Service(api_app.config).reject_draft(ids["drafts"][1], reviewer_user_id=ids["user"])
        session = db.session.get(Design, ids["session"])
        assert session.status == "rejected"
        assert all(d.status == "rejected" for d in session.drafts)
        assert ReviewRecord.query.count() == len(ids["drafts"])


def test_stale_web_edit_keeps_old_revision_and_cannot_retry_overwrite(api_app, review_catalog, monkeypatch):
    ids = review_catalog
    with api_app.app_context():
        draft = db.session.get(Draft, ids["drafts"][0])
        form = {**payload(draft), "draft_revision":str(draft.revision),
                "session_revision":str(draft.session.review_revision)}
        Service(api_app.config).update_draft(draft.id, {**payload(draft), "title":"Demo newer review title"},
                                           reviewer_user_id=ids["user"])
    client = api_app.test_client()
    assert client.post("/auth/login", data={"email":"concurrent@example.test", "password":"demo-password"}).status_code == 302
    rendered = {}
    def render(_template, **context):
        rendered.update(context)
        return "stale review form"
    monkeypatch.setattr("app.blueprints.ai_test_design.routes.render_template", render)
    for _ in range(2):
        response = client.post(f"/ai-test-design/drafts/{ids['drafts'][0]}/edit", data=form)
        assert response.status_code == 409
        assert str(rendered["draft_revision"]) == form["draft_revision"]
        assert str(rendered["session_revision"]) == form["session_revision"]
    with api_app.app_context():
        assert db.session.get(Draft, ids["drafts"][0]).title == "Demo newer review title"
        assert ReviewRecord.query.count() == 1


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_stale_or_missing_web_review_versions_do_not_write(api_app, review_catalog, action):
    ids = review_catalog
    with api_app.app_context():
        draft = db.session.get(Draft, ids["drafts"][0])
        form = {"draft_revision":str(draft.revision), "session_revision":str(draft.session.review_revision)}
        Service(api_app.config).update_draft(draft.id, payload(draft), reviewer_user_id=ids["user"])
    client = api_app.test_client()
    client.post("/auth/login", data={"email":"concurrent@example.test", "password":"demo-password"})
    for data in ({}, form):
        response = client.post(f"/ai-test-design/drafts/{ids['drafts'][0]}/{action}", data=data)
        assert response.status_code == 302
        with api_app.app_context():
            assert db.session.get(Draft, ids["drafts"][0]).status == "pending"
            assert Case.query.count() == ids["initial_case_count"]
            assert ReviewRecord.query.count() == 1
