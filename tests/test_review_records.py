import json
from types import SimpleNamespace

import pytest
from flask_login import login_user
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db
from app.models import (
    Project,
    TestCase as ModelTestCase,
    TestCaseDraft as ModelTestCaseDraft,
    TestDesignSession as ModelTestDesignSession,
    User,
    Version,
)
from app.services.test_design.mock_provider import MockTestDesignProvider
from app.services.test_design.quality import score_test_design
from app.services.test_design.schemas import (
    DraftEditInput,
    TestDesignContext as DesignContext,
)
from app.services.workflow_errors import (
    WorkflowConflictError,
    WorkflowPersistenceError,
)


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": (
                f"sqlite:///{(tmp_path / 'review_records.sqlite').as_posix()}"
            ),
            "AI_ENABLED": False,
            "AI_PROVIDER": "mock",
            "DEEPSEEK_API_KEY": "",
            "DEEPSEEK_MODEL": "",
            "SECRET_KEY": "review-session-signing-value",
            "WTF_CSRF_ENABLED": False,
        }
    )
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def catalog(app):
    with app.app_context():
        project = Project(name="Demo review project", code="DEMO-REVIEW")
        reviewer = User(
            username="demo_reviewer",
            email="demo-reviewer@example.test",
            password_hash="demo-not-used-for-login",
        )
        db.session.add_all((project, reviewer))
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo review version",
            code="FW_DEMO_REVIEW",
        )
        db.session.add(version)
        db.session.commit()
        return {
            "project_id": project.id,
            "version_id": version.id,
            "reviewer_id": reviewer.id,
        }


@pytest.fixture()
def draft_id(app, catalog):
    """A legacy generated draft also needs real audit evidence when reviewed."""
    with app.app_context():
        context = DesignContext(
            title="Demo review draft",
            requirement_text="Sample mock audio volume control with visible status.",
        )
        result = MockTestDesignProvider().generate(context)
        session = ModelTestDesignSession(
            project_id=catalog["project_id"],
            version_id=catalog["version_id"],
            title=context.title,
            requirement_text=context.requirement_text,
            provider="mock",
            prompt_version="test-design-v1",
            quality_score=score_test_design(result).quality_score,
            test_points_json=json.dumps(
                [point.model_dump(mode="json") for point in result.test_points]
            ),
            limitations_json=json.dumps(result.limitations),
        )
        session.drafts = [
            ModelTestCaseDraft(**data.model_dump(mode="json"))
            for data in result.case_drafts
        ]
        db.session.add(session)
        db.session.commit()
        return session.drafts[0].id


def _editable_payload(draft, **changes):
    data = {
        field: getattr(draft, field)
        for field in DraftEditInput.model_fields
    }
    data["precondition"] = draft.precondition or ""
    data.update(changes)
    return data


def _generated_session(app, catalog):
    from app.services.test_design_service import TestDesignService

    service = TestDesignService(app.config)
    session = service.create_session(
        project_id=catalog["project_id"],
        version_id=catalog["version_id"],
        title="Demo human review evidence",
        requirement_text="Sample mock audio volume control with visible status.",
    )
    return service, session


def test_draft_snapshot_contains_nine_content_fields_and_review_state(app, draft_id):
    from app.services.test_design.reviews import draft_snapshot

    with app.app_context():
        draft = db.session.get(ModelTestCaseDraft, draft_id)
        draft.precondition = None

        snapshot = draft_snapshot(draft)

        assert snapshot == {
            **_editable_payload(draft),
            "status": "pending",
            "accepted_test_case_id": None,
        }
        assert len(snapshot) == 11
        assert snapshot["precondition"] == ""
        draft.title = "Changed sample title"
        assert snapshot["title"] != draft.title


def test_build_review_record_captures_detached_snapshots_and_sorted_changes(
    app, catalog, draft_id
):
    from app.services.test_design.reviews import build_review_record, draft_snapshot

    with app.app_context():
        draft = db.session.get(ModelTestCaseDraft, draft_id)
        reviewer = db.session.get(User, catalog["reviewer_id"])
        before = draft_snapshot(draft)
        draft.title = "Sample manually corrected title"
        draft.expected_result = "The mock displayed status shows volume 4."

        record = build_review_record(
            draft, reviewer, "edit", before, 85, 95, comment="Checked the result."
        )

        assert inspect(record).transient
        assert record.draft is draft
        assert record.reviewer_user_id == reviewer.id
        assert record.action == "edit"
        assert record.score_before == 85
        assert record.score_after == 95
        assert record.comment == "Checked the result."
        assert json.loads(record.changed_fields_json) == ["expected_result", "title"]
        assert record.changed_field_count == 2
        assert json.loads(record.before_snapshot_json) == before
        assert json.loads(record.after_snapshot_json) == draft_snapshot(draft)
        before["title"] = "Changed later by the caller"
        assert json.loads(record.before_snapshot_json)["title"] != before["title"]


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_status_and_accepted_link_changes_do_not_count_as_content_edits(
    app, catalog, draft_id, action
):
    from app.services.test_design.reviews import build_review_record, draft_snapshot

    with app.app_context():
        draft = db.session.get(ModelTestCaseDraft, draft_id)
        reviewer = db.session.get(User, catalog["reviewer_id"])
        before = draft_snapshot(draft)
        draft.status = "accepted" if action == "accept" else "rejected"
        draft.accepted_test_case_id = 123 if action == "accept" else None

        record = build_review_record(draft, reviewer, action, before, 90, 90)

        assert record.changed_field_count == 0
        assert json.loads(record.changed_fields_json) == []
        assert json.loads(record.before_snapshot_json)["status"] == "pending"
        assert json.loads(record.after_snapshot_json)["status"] == draft.status


def test_nullable_precondition_normalization_does_not_count_as_an_edit(
    app, catalog, draft_id
):
    from app.services.test_design.reviews import build_review_record, draft_snapshot

    with app.app_context():
        draft = db.session.get(ModelTestCaseDraft, draft_id)
        reviewer = db.session.get(User, catalog["reviewer_id"])
        draft.precondition = None
        before = draft_snapshot(draft)
        draft.precondition = ""
        record = build_review_record(draft, reviewer, "edit", before, 80, 80)
        assert record.changed_field_count == 0


def test_resolve_reviewer_accepts_existing_trusted_internal_user(app, catalog):
    from app.services.test_design.reviews import resolve_reviewer

    with app.app_context():
        reviewer = resolve_reviewer(catalog["reviewer_id"])
        assert isinstance(reviewer, User)
        assert reviewer.id == catalog["reviewer_id"]


def test_resolve_reviewer_uses_real_authenticated_user(app, catalog):
    from app.services.test_design.reviews import resolve_reviewer

    with app.test_request_context():
        reviewer = db.session.get(User, catalog["reviewer_id"])
        login_user(reviewer)
        assert resolve_reviewer() is reviewer


def test_resolve_reviewer_rejects_anonymous_request(app):
    from app.services.test_design.reviews import (
        ReviewAuthenticationError,
        resolve_reviewer,
    )

    with app.test_request_context(), pytest.raises(ReviewAuthenticationError):
        resolve_reviewer()


def test_resolve_reviewer_rejects_missing_identity_outside_request(app):
    from app.services.test_design.reviews import (
        ReviewAuthenticationError,
        resolve_reviewer,
    )

    with app.app_context(), pytest.raises(ReviewAuthenticationError):
        resolve_reviewer()


@pytest.mark.parametrize("user_id", [0, -1, 999999, "invalid", True, 1.5, [], {}])
def test_resolve_reviewer_rejects_invalid_trusted_identity(app, user_id):
    from app.services.test_design.reviews import (
        ReviewAuthenticationError,
        resolve_reviewer,
    )

    with app.app_context(), pytest.raises(ReviewAuthenticationError):
        resolve_reviewer(user_id)


def test_invalid_explicit_identity_does_not_fall_back_to_logged_in_user(app, catalog):
    from app.services.test_design.reviews import (
        ReviewAuthenticationError,
        resolve_reviewer,
    )

    with app.test_request_context():
        login_user(db.session.get(User, catalog["reviewer_id"]))
        with pytest.raises(ReviewAuthenticationError):
            resolve_reviewer(999999)


def test_resolve_reviewer_rechecks_user_still_exists(app, catalog):
    from app.services.test_design.reviews import (
        ReviewAuthenticationError,
        resolve_reviewer,
    )

    with app.test_request_context():
        reviewer = db.session.get(User, catalog["reviewer_id"])
        login_user(reviewer)
        db.session.delete(reviewer)
        db.session.commit()
        with pytest.raises(ReviewAuthenticationError):
            resolve_reviewer()


@pytest.mark.parametrize(
    ("comment", "expected"),
    [(None, None), (" \n ", None), ("  Review checked. \n", "Review checked."),
     ("校" * 1000, "校" * 1000)],
    ids=["absent", "blank", "trimmed", "max-unicode-length"],
)
def test_validate_comment_normalizes_optional_bounded_feedback(comment, expected):
    from app.services.test_design.reviews import validate_comment

    assert validate_comment(comment, {}) == expected


@pytest.mark.parametrize(
    "comment", ["x" * 1001, 123, ["comment"]],
    ids=["oversized", "integer", "list"],
)
def test_validate_comment_rejects_oversized_or_non_text_feedback(comment):
    from app.services.test_design.reviews import validate_comment

    with pytest.raises(ValueError):
        validate_comment(comment, {})


@pytest.mark.parametrize(
    "comment",
    [
        "api_key=sk-FAKE1234567890ABCDEF",
        "Authorization: Bearer demo-private-value",
        '{"headers": {"Authorization": "Bearer demo-private-value"}}',
        "X-API-Key: demo-private-value",
        "reviewed using opaque-provider-credential-value",
        "reviewed using opaque-signing-credential-value",
    ],
)
def test_validate_comment_rejects_sensitive_values_with_safe_errors(comment):
    from app.services.test_design.reviews import validate_comment

    config = {
        "DEEPSEEK_API_KEY": "opaque-provider-credential-value",
        "SECRET_KEY": "opaque-signing-credential-value",
    }
    with pytest.raises(ValueError) as error:
        validate_comment(comment, config)
    assert comment not in str(error.value)
    assert all(value not in str(error.value) for value in config.values())


def test_review_metrics_count_unique_edited_drafts_and_all_edit_operations():
    from app.services.test_design.reviews import review_metrics

    def record(action, changed):
        return SimpleNamespace(action=action, changed_field_count=changed)

    drafts = [
        SimpleNamespace(
            status="accepted",
            review_records=[record("edit", 2), record("edit", 1), record("accept", 0)],
        ),
        SimpleNamespace(status="rejected", review_records=[record("reject", 0)]),
        SimpleNamespace(status="pending", review_records=[record("edit", 0)]),
        SimpleNamespace(status="pending", review_records=[]),
    ]

    assert review_metrics(iter(drafts)) == {
        "total_drafts": 4,
        "edited_drafts": 1,
        "edit_rate": 0.25,
        "average_changed_fields": 1.5,
        "accepted_count": 1,
        "rejected_count": 1,
        "acceptance_rate": 0.25,
        "rejection_rate": 0.25,
        "review_count": 5,
    }


def test_review_metrics_empty_denominators_are_zero():
    from app.services.test_design.reviews import review_metrics

    assert review_metrics([]) == {
        "total_drafts": 0,
        "edited_drafts": 0,
        "edit_rate": 0.0,
        "average_changed_fields": 0.0,
        "accepted_count": 0,
        "rejected_count": 0,
        "acceptance_rate": 0.0,
        "rejection_rate": 0.0,
        "review_count": 0,
    }


@pytest.mark.parametrize("action", ["edit", "reject"])
@pytest.mark.parametrize("sensitive", ["Authorization: Bearer arbitrary-private-value", "api_key=sk-PRIVATE1234567890", "legacy-configured-private-value"])
def test_legacy_sensitive_content_is_redacted_in_review_evidence(app, catalog, action, sensitive):
    from app.models import ReviewRecord
    with app.app_context():
        app.config["DEEPSEEK_API_KEY"] = "legacy-configured-private-value"
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        draft.expected_result = "Demo displayed status " + sensitive
        db.session.commit()
        if action == "edit":
            service.update_draft(draft.id, _editable_payload(draft, expected_result="Demo displayed expected status"), reviewer_user_id=catalog["reviewer_id"])
        else:
            service.reject_draft(draft.id, reviewer_user_id=catalog["reviewer_id"])
        record = ReviewRecord.query.one()
        assert sensitive not in record.before_snapshot_json + record.after_snapshot_json
        before = json.loads(record.before_snapshot_json)
        after = json.loads(record.after_snapshot_json)
        assert before["expected_result"] == "[redacted sensitive content]"
        assert before["redacted_fields"] == ["expected_result"]
        assert record.changed_field_count == (1 if action == "edit" else 0)
        assert ("redacted_fields" in after) is (action == "reject")


def test_service_edit_then_accept_records_content_status_scores_and_reviewer(
    app, catalog
):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import draft_snapshot, review_metrics

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        initial_snapshot = draft_snapshot(draft)
        initial_score = service.assessment_for_session(session).quality_score

        service.update_draft(
            draft.id,
            _editable_payload(draft, precondition=""),
            reviewer_user_id=catalog["reviewer_id"],
            comment="  Precondition needs a more precise setup.  ",
        )
        edited_score = service.assessment_for_session(session).quality_score
        edit = ReviewRecord.query.filter_by(draft_id=draft.id, action="edit").one()
        assert edit.reviewer_user_id == catalog["reviewer_id"]
        assert edit.comment == "Precondition needs a more precise setup."
        assert edit.score_before == initial_score
        assert edit.score_after == edited_score
        assert edited_score < initial_score
        assert json.loads(edit.before_snapshot_json) == initial_snapshot
        assert json.loads(edit.after_snapshot_json) == draft_snapshot(draft)
        assert json.loads(edit.changed_fields_json) == ["precondition"]
        assert edit.changed_field_count == 1

        before_accept = draft_snapshot(draft)
        test_case = service.accept_draft(
            draft.id,
            reviewer_user_id=catalog["reviewer_id"],
            comment="Accepted for the sample checklist.",
        )
        acceptance = ReviewRecord.query.filter_by(
            draft_id=draft.id, action="accept"
        ).one()
        assert acceptance.reviewer_user_id == catalog["reviewer_id"]
        assert acceptance.score_before == edited_score
        assert acceptance.score_after == edited_score
        assert acceptance.changed_field_count == 0
        assert json.loads(acceptance.before_snapshot_json) == before_accept
        assert json.loads(acceptance.after_snapshot_json) == draft_snapshot(draft)
        assert json.loads(acceptance.after_snapshot_json)["accepted_test_case_id"] == (
            test_case.id
        )
        assert test_case.title == draft.title
        metrics = review_metrics(session.drafts)
        assert metrics["edited_drafts"] == 1
        assert metrics["accepted_count"] == 1
        assert metrics["review_count"] == 2
        assert metrics["acceptance_rate"] == 1 / len(session.drafts)

        with pytest.raises(WorkflowConflictError):
            service.accept_draft(draft.id, reviewer_user_id=catalog["reviewer_id"])
        assert ReviewRecord.query.count() == 2
        assert ModelTestCase.query.count() == 1


def test_service_edit_then_reject_keeps_both_evidence_records(app, catalog):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import draft_snapshot

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        service.update_draft(
            draft.id,
            _editable_payload(draft, title="Sample human corrected audio case"),
            reviewer_user_id=catalog["reviewer_id"],
        )
        before = draft_snapshot(draft)
        score = service.assessment_for_session(session).quality_score

        service.reject_draft(
            draft.id,
            reviewer_user_id=catalog["reviewer_id"],
            comment="Sample coverage is redundant.",
        )

        rejection = ReviewRecord.query.filter_by(
            draft_id=draft.id, action="reject"
        ).one()
        assert rejection.reviewer_user_id == catalog["reviewer_id"]
        assert json.loads(rejection.before_snapshot_json) == before
        assert json.loads(rejection.after_snapshot_json) == draft_snapshot(draft)
        assert rejection.score_before == rejection.score_after == score
        assert rejection.changed_field_count == 0
        assert draft.status == "rejected"
        assert draft.accepted_test_case_id is None
        assert ReviewRecord.query.filter_by(draft_id=draft.id).count() == 2
        assert ModelTestCase.query.count() == 0


def test_service_noop_edit_records_review_without_counting_content_change(app, catalog):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import review_metrics

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        service.update_draft(
            draft.id,
            _editable_payload(draft),
            reviewer_user_id=catalog["reviewer_id"],
        )
        record = ReviewRecord.query.one()
        assert record.changed_field_count == 0
        assert record.score_before == record.score_after
        assert review_metrics(session.drafts)["edited_drafts"] == 0
        assert review_metrics(session.drafts)["review_count"] == 1


@pytest.mark.parametrize("action", ["edit", "accept", "reject"])
def test_service_rejects_anonymous_review_before_any_mutation(app, catalog, action):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import draft_snapshot

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        before = draft_snapshot(draft)
        with pytest.raises(ValueError):
            if action == "edit":
                service.update_draft(
                    draft.id,
                    _editable_payload(draft, title="Sample unauthorized change"),
                )
            else:
                getattr(service, f"{action}_draft")(draft.id)
        assert draft_snapshot(draft) == before
        assert ReviewRecord.query.count() == 0
        assert ModelTestCase.query.count() == 0


@pytest.mark.parametrize("action", ["edit", "accept", "reject"])
def test_service_unsafe_comment_is_rejected_before_mutation(app, catalog, action):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import draft_snapshot

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        before = draft_snapshot(draft)
        with pytest.raises(ValueError) as error:
            kwargs = {
                "reviewer_user_id": catalog["reviewer_id"],
                "comment": "review-session-signing-value",
            }
            if action == "edit":
                service.update_draft(
                    draft.id,
                    _editable_payload(draft, title="Sample unauthorized change"),
                    **kwargs,
                )
            else:
                getattr(service, f"{action}_draft")(draft.id, **kwargs)
        assert "review-session-signing-value" not in str(error.value)
        assert draft_snapshot(draft) == before
        assert ReviewRecord.query.count() == 0
        assert ModelTestCase.query.count() == 0


@pytest.mark.parametrize("action", ["edit", "accept", "reject"])
def test_service_review_and_business_change_roll_back_together(
    app, catalog, monkeypatch, action
):
    from app.models import ReviewRecord
    from app.services.test_design.reviews import draft_snapshot

    with app.app_context():
        service, session = _generated_session(app, catalog)
        draft = session.drafts[0]
        draft_id = draft.id
        session_id = session.id
        before = draft_snapshot(draft)
        initial_score = session.quality_score
        initial_status = session.status

        def fail_commit():
            raise OperationalError("commit", {}, Exception("sample write failed"))

        monkeypatch.setattr(db.session, "commit", fail_commit)
        with pytest.raises(WorkflowPersistenceError):
            kwargs = {"reviewer_user_id": catalog["reviewer_id"]}
            if action == "edit":
                service.update_draft(
                    draft.id,
                    _editable_payload(draft, precondition=""),
                    **kwargs,
                )
            else:
                getattr(service, f"{action}_draft")(draft.id, **kwargs)
        db.session.expire_all()
        reloaded = db.session.get(ModelTestCaseDraft, draft_id)
        reloaded_session = db.session.get(ModelTestDesignSession, session_id)
        assert draft_snapshot(reloaded) == before
        assert reloaded_session.quality_score == initial_score
        assert reloaded_session.status == initial_status
        assert ReviewRecord.query.count() == 0
        assert ModelTestCase.query.count() == 0
