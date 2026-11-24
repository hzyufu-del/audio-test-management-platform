import pytest
from flask import Flask
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import models
from app.extensions import db


RUN_FIELDS = {
    "request_key",
    "request_fingerprint",
    "active_request_scope",
    "validation_summary_json",
    "id",
    "session_id",
    "project_id",
    "version_id",
    "title",
    "requirement_text",
    "provider",
    "provider_model",
    "prompt_version",
    "prompt_hash",
    "requirement_hash",
    "status",
    "started_at",
    "finished_at",
    "latency_ms",
    "input_chars",
    "output_chars",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "finish_reason",
    "temperature",
    "max_tokens",
    "error_type",
    "error_message",
    "structured_output_json",
    "created_at",
}
REVIEW_FIELDS = {
    "id",
    "draft_id",
    "reviewer_user_id",
    "action",
    "before_snapshot_json",
    "after_snapshot_json",
    "score_before",
    "score_after",
    "changed_fields_json",
    "changed_field_count",
    "comment",
    "created_at",
}
NULL_RUN_METADATA = {
    "request_key",
    "request_fingerprint",
    "active_request_scope",
    "validation_summary_json",
    "provider_model",
    "finished_at",
    "latency_ms",
    "input_chars",
    "output_chars",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "finish_reason",
    "temperature",
    "max_tokens",
    "error_type",
    "error_message",
    "structured_output_json",
}


def evidence_model(name):
    model = getattr(models, name, None)
    assert model is not None, f"Experimental evidence model {name} is missing"
    return model


@pytest.fixture()
def app(tmp_path):
    application = Flask("experiment-models")
    application.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'evidence.sqlite').as_posix()}",
        }
    )
    db.init_app(application)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def catalog():
    project = models.Project(name="Demo evidence", code="DEMO-EVIDENCE")
    db.session.add(project)
    db.session.flush()
    version = models.Version(project_id=project.id, name="Demo V1", code="V1")
    user = models.User(
        username="reviewer", email="reviewer@example.com", password_hash="demo"
    )
    db.session.add_all([version, user])
    db.session.flush()
    session = models.TestDesignSession(
        project_id=project.id,
        version_id=version.id,
        title="Demo requirement",
        requirement_text="Sample playback requirement.",
        provider="mock",
        prompt_version="test-design-v1",
        quality_score=100,
        test_points_json="[]",
        limitations_json="[]",
    )
    db.session.add(session)
    db.session.flush()
    draft = add_draft(session)
    db.session.commit()
    return project, version, user, session, draft


def add_draft(session, **overrides):
    values = dict(
        session_id=session.id,
        suggested_code="TC_DEMO_001",
        title="Demo playback",
        module="Audio",
        priority="P1",
        case_type="checklist",
        steps="Play sample audio.",
        expected_result="Sample audio is audible.",
        scenario_type="normal",
    )
    values.update(overrides)
    draft = models.TestCaseDraft(**values)
    db.session.add(draft)
    db.session.flush()
    return draft


def add_run(project, version, *, session=None, flush=True, **overrides):
    values = dict(
        project_id=project.id,
        version_id=version.id,
        session_id=session.id if session else None,
        title="Demo requirement",
        requirement_text="Sample playback requirement.",
        provider="mock",
        prompt_version="test-design-v1",
        prompt_hash="a" * 64,
        requirement_hash="b" * 64,
        status="running",
    )
    values.update(overrides)
    run = evidence_model("GenerationRun")(**values)
    db.session.add(run)
    if flush:
        db.session.flush()
    return run


def add_review(draft, user, *, flush=True, **overrides):
    values = dict(
        draft_id=draft.id,
        reviewer_user_id=user.id,
        action="edit",
        before_snapshot_json='{"title":"Demo playback","status":"pending"}',
        after_snapshot_json='{"title":"Demo playback","status":"pending"}',
        score_before=100,
        score_after=100,
        changed_fields_json="[]",
        changed_field_count=0,
    )
    values.update(overrides)
    review = evidence_model("ReviewRecord")(**values)
    db.session.add(review)
    if flush:
        db.session.flush()
    return review


def test_evidence_schema_fields_relationships_and_nullable_metadata(app):
    with app.app_context():
        run_model = evidence_model("GenerationRun")
        review_model = evidence_model("ReviewRecord")
        inspector = inspect(db.engine)
        assert {
            c["name"] for c in inspector.get_columns("generation_run")
        } == RUN_FIELDS
        assert {
            c["name"] for c in inspector.get_columns("review_record")
        } == REVIEW_FIELDS
        project, version, user, session, draft = catalog()
        run = add_run(project, version, session=session)
        draft.generation_run = run
        review = add_review(draft, user)
        db.session.commit()

        assert session.generation_runs == [run]
        assert run.session is session
        assert run.project is project
        assert run.version is version
        assert run.drafts == [draft]
        assert draft.generation_run_id == run.id
        assert draft.review_records == [review]
        assert review.draft is draft
        assert review.reviewer is user
        assert project.generation_runs == [run]
        assert version.generation_runs == [run]
        assert user.review_records == [review]
        assert run_model.query.count() == review_model.query.count() == 1
        assert run.started_at is not None and run.created_at is not None
        assert review.created_at is not None and review.comment is None
        assert all(getattr(run, field) is None for field in NULL_RUN_METADATA)


def test_initial_failure_run_can_exist_without_session(app):
    with app.app_context():
        project, version, _, _, draft = catalog()
        run = add_run(project, version, status="failed", error_type="validation")
        db.session.commit()
        assert run.session_id is None and run.session is None
        assert run.title == "Demo requirement"
        assert run.requirement_text == "Sample playback requirement."
        assert draft.generation_run_id is None


@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "version_id",
        "title",
        "requirement_text",
        "provider",
        "prompt_version",
        "prompt_hash",
        "requirement_hash",
    ],
)
def test_generation_run_rejects_missing_required_input_fields(app, field):
    with app.app_context():
        project, version, _, _, _ = catalog()
        add_run(project, version, flush=False, **{field: None})
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize(
    "field",
    [
        "draft_id",
        "reviewer_user_id",
        "action",
        "before_snapshot_json",
        "after_snapshot_json",
        "score_before",
        "score_after",
        "changed_fields_json",
        "changed_field_count",
    ],
)
def test_review_record_rejects_missing_required_evidence_fields(app, field):
    with app.app_context():
        _, _, user, _, draft = catalog()
        add_review(draft, user, flush=False, **{field: None})
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize(
    "values",
    [
        {"status": "unknown"},
        {"provider": "other"},
    ],
)
def test_generation_run_rejects_invalid_status_or_provider(app, values):
    with app.app_context():
        project, version, _, _, _ = catalog()
        add_run(project, version, flush=False, **values)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize(
    "values",
    [
        {"action": "unknown"},
        {"changed_field_count": -1},
        {"changed_field_count": 10},
        {"score_before": -1},
        {"score_before": 101},
        {"score_after": -1},
        {"score_after": 101},
    ],
)
def test_review_record_rejects_invalid_action_count_or_score(app, values):
    with app.app_context():
        _, _, user, _, draft = catalog()
        add_review(draft, user, flush=False, **values)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("action", ["edit", "accept", "reject"])
def test_review_record_accepts_actions_and_boundary_scores(app, action):
    with app.app_context():
        _, _, user, _, draft = catalog()
        review = add_review(
            draft,
            user,
            action=action,
            score_before=0,
            score_after=100,
            changed_field_count=9,
        )
        db.session.commit()
        assert review.action == action
        assert review.changed_field_count == 9


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_running_generation_run_can_reach_terminal_status_once(app, status):
    with app.app_context():
        project, version, _, session, _ = catalog()
        run = add_run(project, version)
        db.session.commit()
        run.session_id = session.id if status == "succeeded" else None
        run.status = status
        run.finished_at = models.utc_now()
        run.latency_ms = 10
        db.session.commit()
        assert run.status == status and run.latency_ms == 10

        run.status = "running"
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()
        assert run.status == status


@pytest.mark.parametrize("status", ["succeeded", "failed"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Changed"),
        ("structured_output_json", "{}"),
        ("id", 999),
    ],
)
def test_terminal_generation_run_rejects_orm_column_updates(app, status, field, value):
    with app.app_context():
        project, version, _, _, _ = catalog()
        run = add_run(project, version, status=status)
        db.session.commit()
        db.session.expire(run)
        setattr(run, field, value)
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_terminal_generation_run_rejects_orm_delete(app, status):
    with app.app_context():
        project, version, _, _, _ = catalog()
        run = add_run(project, version, status=status)
        db.session.commit()
        db.session.delete(run)
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()


def test_running_generation_run_allows_orm_update_and_delete(app):
    with app.app_context():
        project, version, _, _, _ = catalog()
        run = add_run(project, version)
        db.session.commit()
        run.provider_model = "mock-model"
        db.session.commit()
        assert run.provider_model == "mock-model"
        db.session.delete(run)
        db.session.commit()
        assert evidence_model("GenerationRun").query.count() == 0


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_review_record_is_immutable_after_creation(app, operation):
    with app.app_context():
        _, _, user, _, draft = catalog()
        review = add_review(draft, user)
        db.session.commit()
        if operation == "update":
            review.comment = "Changed later"
        else:
            db.session.delete(review)
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()
        assert evidence_model("ReviewRecord").query.count() == 1


def test_terminal_run_accepts_new_draft_relationship_without_mutating_evidence(app):
    with app.app_context():
        project, version, _, session, _ = catalog()
        run = add_run(project, version, session=session, status="succeeded")
        db.session.commit()
        draft = add_draft(session, suggested_code="TC_DEMO_002", generation_run=run)
        db.session.commit()
        assert run.drafts == [draft]


@pytest.mark.parametrize(
    "kind,field",
    [
        ("run", "session_id"),
        ("run", "project_id"),
        ("run", "version_id"),
        ("review", "draft_id"),
        ("review", "reviewer_user_id"),
        ("draft", "generation_run_id"),
    ],
)
def test_evidence_foreign_keys_reject_missing_sources(app, kind, field):
    with app.app_context():
        project, version, user, _, draft = catalog()
        if kind == "run":
            add_run(project, version, flush=False, **{field: 99999})
        elif kind == "review":
            add_review(draft, user, flush=False, **{field: 99999})
        else:
            evidence_model("GenerationRun")
            draft.generation_run_id = 99999
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_evidence_foreign_keys_are_explicitly_restrict_and_old_cascade_remains(app):
    with app.app_context():
        evidence_model("GenerationRun")
        evidence_model("ReviewRecord")
        inspector = inspect(db.engine)
        for table in ("generation_run", "review_record"):
            assert all(
                fk["options"].get("ondelete") == "RESTRICT"
                for fk in inspector.get_foreign_keys(table)
            )
        draft_keys = {
            tuple(fk["constrained_columns"]): fk
            for fk in inspector.get_foreign_keys("test_case_draft")
        }
        assert draft_keys[("generation_run_id",)]["options"]["ondelete"] == "RESTRICT"
        assert draft_keys[("session_id",)]["options"]["ondelete"] == "CASCADE"


@pytest.mark.parametrize(
    "table",
    [
        "test_design_session",
        "test_case_draft",
        "user",
        "generation_run",
        "version",
        "project",
    ],
)
def test_foreign_keys_prevent_deleting_evidence_sources(app, table):
    with app.app_context():
        project, version, user, session, draft = catalog()
        run = add_run(project, version, session=session, status="succeeded")
        draft.generation_run = run
        add_review(draft, user)
        db.session.commit()
        ids = {
            "project": project.id,
            "version": version.id,
            "user": user.id,
            "test_design_session": session.id,
            "test_case_draft": draft.id,
            "generation_run": run.id,
        }
        with pytest.raises(IntegrityError):
            db.session.execute(
                text(f'DELETE FROM "{table}" WHERE id = :id'), {"id": ids[table]}
            )
        db.session.rollback()
        assert evidence_model("GenerationRun").query.count() == 1
        assert evidence_model("ReviewRecord").query.count() == 1


@pytest.mark.parametrize("parent", ["session", "draft", "user"])
@pytest.mark.parametrize("loaded", [False, True])
def test_orm_parent_delete_preserves_evidence_with_loaded_or_unloaded_relationships(
    app,
    parent,
    loaded,
):
    with app.app_context():
        project, version, user, session, draft = catalog()
        run = add_run(project, version, session=session, status="succeeded")
        draft.generation_run = run
        add_review(draft, user)
        db.session.commit()
        if loaded:
            assert session.generation_runs
            assert draft.review_records
            assert user.review_records
            assert session.drafts
        target = {"session": session, "draft": draft, "user": user}[parent]
        db.session.delete(target)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert run.session_id == session.id
        assert evidence_model("ReviewRecord").query.one().reviewer_user_id == user.id


def test_historical_session_without_evidence_still_cascades_drafts(app):
    with app.app_context():
        _, _, _, session, draft = catalog()
        draft_id = draft.id
        session_id = session.id
        db.session.delete(session)
        db.session.commit()
        assert db.session.get(models.TestDesignSession, session_id) is None
        assert db.session.get(models.TestCaseDraft, draft_id) is None
