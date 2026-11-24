import pytest
from flask import Flask
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.extensions import db, migrate


PREVIOUS_REVISION = "c5d8a9e4f2b1"
EVIDENCE_REVISION = "d7e2f6a9b301"


def make_app(tmp_path, name):
    app = Flask("experiment-migration")
    app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / name).as_posix()}",
        }
    )
    db.init_app(app)
    migrate.init_app(app, db)
    return app


def seed_historical_rows():
    db.session.execute(
        text(
            "INSERT INTO project (id, name, code, status, created_at, updated_at) "
            "VALUES (1, 'Old demo', 'OLD-DEMO', 'active', '2026-07-26', '2026-07-26')"
        )
    )
    db.session.execute(
        text(
            "INSERT INTO version (id, project_id, name, code, release_type, status, created_at, "
            "updated_at) VALUES (1, 1, 'Old version', 'V1', 'sample', 'testing', "
            "'2026-07-26', '2026-07-26')"
        )
    )
    db.session.execute(
        text(
            "INSERT INTO test_design_session (id, project_id, version_id, title, requirement_text, "
            "status, provider, prompt_version, quality_score, test_points_json, limitations_json, "
            "created_at, updated_at) VALUES (1, 1, 1, 'Old sample', 'Original sample requirement', "
            "'generated', 'mock', 'test-design-v1', 95, '[]', '[]', '2026-07-26', '2026-07-26')"
        )
    )
    db.session.execute(
        text(
            "INSERT INTO test_case_draft (id, session_id, suggested_code, title, module, priority, "
            "case_type, precondition, steps, expected_result, scenario_type, status, created_at, "
            "updated_at) VALUES (1, 1, 'TC_OLD_001', 'Old sample case', 'Audio', 'P1', 'checklist', "
            "'Original precondition', 'Original steps', 'Original result', 'normal', 'pending', "
            "'2026-07-26', '2026-07-26')"
        )
    )
    db.session.commit()


def test_evidence_migration_fresh_upgrade_schema_and_alembic_check(tmp_path):
    app = make_app(tmp_path, "evidence_fresh.sqlite")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", EVIDENCE_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        inspector = inspect(db.engine)
        assert {"generation_run", "review_record"} <= set(inspector.get_table_names())
        run_columns = {c["name"]: c for c in inspector.get_columns("generation_run")}
        assert run_columns["session_id"]["nullable"] is True
        assert run_columns["project_id"]["nullable"] is False
        assert run_columns["version_id"]["nullable"] is False
        for field in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "finish_reason",
            "temperature",
            "provider_model",
        ):
            assert run_columns[field]["nullable"] is True
        review_columns = {c["name"]: c for c in inspector.get_columns("review_record")}
        assert review_columns["reviewer_user_id"]["nullable"] is False
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
        assert db.session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    # Preserve the historical-revision assertions above, then compare the
    # current ORM only after applying subsequent additive migrations.
    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "upgrade", "head"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "check"])
    assert result.exit_code == 0, result.output


def test_evidence_migration_preserves_old_rows_without_fabricating_evidence(tmp_path):
    app = make_app(tmp_path, "evidence_historical.sqlite")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        seed_historical_rows()
        old_session = (
            db.session.execute(text("SELECT * FROM test_design_session"))
            .mappings()
            .one()
        )
        old_draft = (
            db.session.execute(text("SELECT * FROM test_case_draft")).mappings().one()
        )
        old_session = dict(old_session)
        old_draft = dict(old_draft)
        db.session.remove()
    result = runner.invoke(args=["db", "upgrade", EVIDENCE_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert (
            dict(
                db.session.execute(text("SELECT * FROM test_design_session"))
                .mappings()
                .one()
            )
            == old_session
        )
        upgraded_draft = dict(
            db.session.execute(text("SELECT * FROM test_case_draft")).mappings().one()
        )
        assert upgraded_draft.pop("generation_run_id") is None
        assert upgraded_draft == old_draft
        assert (
            db.session.execute(text("SELECT COUNT(*) FROM generation_run")).scalar_one()
            == 0
        )
        assert (
            db.session.execute(text("SELECT COUNT(*) FROM review_record")).scalar_one()
            == 0
        )
        assert db.session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    result = runner.invoke(args=["db", "upgrade", "head"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "check"])
    assert result.exit_code == 0, result.output


def test_evidence_migration_downgrade_and_reupgrade_preserve_historical_rows(tmp_path):
    app = make_app(tmp_path, "evidence_cycle.sqlite")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        seed_historical_rows()
    result = runner.invoke(args=["db", "upgrade", EVIDENCE_REVISION])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "downgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        inspector = inspect(db.engine)
        assert "generation_run" not in inspector.get_table_names()
        assert "review_record" not in inspector.get_table_names()
        assert "generation_run_id" not in {
            c["name"] for c in inspector.get_columns("test_case_draft")
        }
        assert (
            db.session.execute(
                text("SELECT requirement_text FROM test_design_session")
            ).scalar_one()
            == "Original sample requirement"
        )
        assert (
            db.session.execute(text("SELECT steps FROM test_case_draft")).scalar_one()
            == "Original steps"
        )
        assert db.session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    result = runner.invoke(args=["db", "upgrade", EVIDENCE_REVISION])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "upgrade", "head"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(args=["db", "check"])
    assert result.exit_code == 0, result.output


def test_migrated_database_enforces_constraints_and_restrict_deletes(tmp_path):
    app = make_app(tmp_path, "evidence_constraints.sqlite")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", EVIDENCE_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        seed_historical_rows()
        insert_run = text(
            "INSERT INTO generation_run (id, session_id, project_id, version_id, title, "
            "requirement_text, provider, prompt_version, prompt_hash, requirement_hash, status, "
            "started_at, created_at) VALUES (1, 1, 1, 1, 'Sample', 'Original sample requirement', "
            "'mock', 'test-design-v1', :prompt_hash, :requirement_hash, :status, "
            "'2026-10-01', '2026-10-01')"
        )
        values = {
            "prompt_hash": "a" * 64,
            "requirement_hash": "b" * 64,
            "status": "unknown",
        }
        with pytest.raises(IntegrityError):
            db.session.execute(insert_run, values)
        db.session.rollback()
        values["status"] = "succeeded"
        db.session.execute(insert_run, values)
        db.session.execute(
            text("UPDATE test_case_draft SET generation_run_id = 1 WHERE id = 1")
        )
        db.session.execute(
            text(
                "INSERT INTO user (id, username, email, password_hash, created_at) "
                "VALUES (1, 'Demo', 'demo@example.com', 'demo', '2026-10-01')"
            )
        )
        insert_review = text(
            "INSERT INTO review_record (id, draft_id, reviewer_user_id, action, before_snapshot_json, "
            "after_snapshot_json, score_before, score_after, changed_fields_json, "
            "changed_field_count, created_at) VALUES (1, 1, 1, :action, '{}', '{}', :score_before, "
            "100, '[]', :changed_field_count, '2026-10-01')"
        )
        db.session.commit()
        for overrides in (
            {"action": "unknown"},
            {"score_before": 101},
            {"changed_field_count": 10},
        ):
            review_values = dict(action="edit", score_before=90, changed_field_count=0)
            review_values.update(overrides)
            with pytest.raises(IntegrityError):
                db.session.execute(insert_review, review_values)
            db.session.rollback()
        db.session.execute(
            insert_review, dict(action="edit", score_before=90, changed_field_count=0)
        )
        db.session.commit()
        for table in (
            "generation_run",
            "test_design_session",
            "test_case_draft",
            "user",
            "project",
            "version",
        ):
            with pytest.raises(IntegrityError):
                db.session.execute(text(f'DELETE FROM "{table}" WHERE id = 1'))
            db.session.rollback()
        assert db.session.execute(text("PRAGMA foreign_key_check")).fetchall() == []
