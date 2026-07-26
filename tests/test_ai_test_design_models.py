import json

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import Project, TestCase as ModelTestCase, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test_design_models.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def add_project_version():
    project = Project(
        name="Mock Test Design Project",
        code="MOCK-TEST-DESIGN",
        status="active",
    )
    db.session.add(project)
    db.session.flush()
    version = Version(
        project_id=project.id,
        name="Demo Test Design Version",
        code="FW_DEMO_TEST_DESIGN",
        status="testing",
    )
    db.session.add(version)
    db.session.flush()
    return project, version


def add_session(project, version, *, flush=True, **overrides):
    from app.models import TestDesignSession

    values = {
        "project_id": project.id,
        "version_id": version.id,
        "title": "Demo audio requirement",
        "requirement_text": (
            "Sample audio volume adjustment requirement for a mock device."
        ),
        "status": "generated",
        "provider": "mock",
        "provider_model": None,
        "prompt_version": "test-design-v1",
        "quality_score": 100,
        "test_points_json": json.dumps([{"title": "Sample point"}]),
        "limitations_json": json.dumps(["Requires human review."]),
    }
    values.update(overrides)
    item = TestDesignSession(**values)
    db.session.add(item)
    if flush:
        db.session.flush()
    return item


def add_draft(session, *, flush=True, **overrides):
    from app.models import TestCaseDraft

    values = {
        "session_id": session.id,
        "suggested_code": "TC_AI_AUDIO_001",
        "title": "Validate sample audio behavior",
        "module": "Audio",
        "priority": "P0",
        "case_type": "checklist",
        "precondition": "Mock device is connected.",
        "steps": "1. Open sample page.\n2. Trigger action.",
        "expected_result": "Displayed sample status updates.",
        "scenario_type": "normal",
        "status": "pending",
    }
    values.update(overrides)
    item = TestCaseDraft(**values)
    db.session.add(item)
    if flush:
        db.session.flush()
    return item


def test_models_expose_required_columns_relationships_and_constraints(app):
    from app.models import TestCaseDraft, TestDesignSession

    with app.app_context():
        inspector = inspect(db.engine)
        session_columns = {
            column["name"]
            for column in inspector.get_columns("test_design_session")
        }
        draft_columns = {
            column["name"]
            for column in inspector.get_columns("test_case_draft")
        }

        assert session_columns == {
            "id",
            "project_id",
            "version_id",
            "title",
            "requirement_text",
            "status",
            "provider",
            "provider_model",
            "prompt_version",
            "quality_score",
            "test_points_json",
            "limitations_json",
            "created_at",
            "updated_at",
        }
        assert draft_columns == {
            "id",
            "session_id",
            "suggested_code",
            "title",
            "module",
            "priority",
            "case_type",
            "precondition",
            "steps",
            "expected_result",
            "scenario_type",
            "status",
            "accepted_test_case_id",
            "created_at",
            "updated_at",
        }

        project, version = add_project_version()
        session = add_session(project, version)
        draft = add_draft(session)
        db.session.commit()

        assert session.project is project
        assert session.version is version
        assert session.drafts == [draft]
        assert draft.session is session
        assert project.test_design_sessions == [session]
        assert version.test_design_sessions == [session]
        assert TestDesignSession.query.one().status == "generated"
        assert TestCaseDraft.query.one().accepted_test_case_id is None


@pytest.mark.parametrize(
    ("model_name", "overrides"),
    [
        ("session", {"status": "unknown"}),
        ("session", {"provider": "other"}),
        ("session", {"quality_score": -1}),
        ("session", {"quality_score": 101}),
        ("draft", {"status": "unknown"}),
        ("draft", {"scenario_type": "chaos"}),
    ],
)
def test_database_rejects_invalid_status_provider_score_and_scenario(
    app,
    model_name,
    overrides,
):
    with app.app_context():
        project, version = add_project_version()
        if model_name == "session":
            add_session(project, version, flush=False, **overrides)
        else:
            session = add_session(project, version)
            add_draft(session, flush=False, **overrides)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_accepted_test_case_can_be_linked_to_only_one_draft(app):
    with app.app_context():
        project, version = add_project_version()
        session = add_session(project, version)
        test_case = ModelTestCase(
            version_id=version.id,
            code="TC_AI_ACCEPTED_001",
            title="Accepted sample case",
            module="Audio",
            priority="P0",
            case_type="checklist",
            precondition="Mock device is connected.",
            steps="1. Open sample page.\n2. Trigger action.",
            expected_result="Displayed sample status updates.",
            status="draft",
        )
        db.session.add(test_case)
        db.session.flush()
        first = add_draft(
            session,
            status="accepted",
            accepted_test_case_id=test_case.id,
        )
        db.session.flush()

        assert first.accepted_test_case is test_case
        add_draft(
            session,
            flush=False,
            suggested_code="TC_AI_AUDIO_002",
            status="accepted",
            accepted_test_case_id=test_case.id,
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_session_delete_removes_drafts_but_not_accepted_test_case(app):
    from app.models import TestCaseDraft, TestDesignSession

    with app.app_context():
        project, version = add_project_version()
        session = add_session(project, version, status="accepted")
        test_case = ModelTestCase(
            version_id=version.id,
            code="TC_AI_PRESERVED_001",
            title="Preserved sample case",
            module="Audio",
            priority="P0",
            case_type="checklist",
            precondition="Mock device is connected.",
            steps="1. Open sample page.\n2. Trigger action.",
            expected_result="Displayed sample status updates.",
            status="draft",
        )
        db.session.add(test_case)
        db.session.flush()
        add_draft(
            session,
            status="accepted",
            accepted_test_case_id=test_case.id,
        )
        db.session.commit()
        session_id = session.id
        test_case_id = test_case.id

        db.session.delete(session)
        db.session.commit()

        assert db.session.get(TestDesignSession, session_id) is None
        assert TestCaseDraft.query.count() == 0
        assert db.session.get(ModelTestCase, test_case_id) is not None
