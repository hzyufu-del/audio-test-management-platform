import json

from app import create_app
from app.extensions import db
from app.models import (
    TestCaseDraft as ModelTestCaseDraft,
    TestDesignSession as ModelTestDesignSession,
)


def test_init_db_seeds_idempotent_sample_test_design_session(tmp_path):
    database_path = tmp_path / "test_design_seed.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )
    with app.app_context():
        db.create_all()

    runner = app.test_cli_runner()
    first = runner.invoke(args=["init-db"])
    second = runner.invoke(args=["init-db"])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output

    with app.app_context():
        assert ModelTestDesignSession.query.count() == 1
        assert ModelTestCaseDraft.query.count() == 3
        session = ModelTestDesignSession.query.one()

        assert session.title == "Demo AI Audio Test Design"
        assert session.provider == "mock"
        assert session.provider_model is None
        assert session.prompt_version == "test-design-v1"
        assert session.status == "generated"
        assert session.project.code.startswith("MOCK-")
        assert session.version.code.startswith("FW_DEMO_")
        assert {draft.status for draft in session.drafts} == {"pending"}
        assert {draft.scenario_type for draft in session.drafts} == {
            "normal",
            "negative",
            "boundary",
        }
        combined = " ".join(
            [
                session.title,
                session.requirement_text,
                session.test_points_json,
                session.limitations_json,
                *[
                    f"{draft.title} {draft.steps} {draft.expected_result}"
                    for draft in session.drafts
                ],
            ]
        ).casefold()
        assert any(marker in combined for marker in ("mock", "demo", "sample"))
        assert "real company" not in combined
        assert isinstance(json.loads(session.test_points_json), list)
        assert isinstance(json.loads(session.limitations_json), list)
