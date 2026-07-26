from sqlalchemy import inspect, text

from app import create_app
from app.extensions import db


PREVIOUS_REVISION = "7c9d0e4f6a21"
TEST_DESIGN_REVISION = "c5d8a9e4f2b1"


def make_app(tmp_path, filename):
    database_path = tmp_path / filename
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )


def schema_snapshot():
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    session_columns = {
        column["name"]: column
        for column in inspector.get_columns("test_design_session")
    }
    draft_columns = {
        column["name"]: column
        for column in inspector.get_columns("test_case_draft")
    }
    session_foreign_keys = {
        tuple(item["constrained_columns"]): (
            item["referred_table"],
            tuple(item["referred_columns"]),
        )
        for item in inspector.get_foreign_keys("test_design_session")
    }
    draft_foreign_keys = {
        tuple(item["constrained_columns"]): (
            item["referred_table"],
            tuple(item["referred_columns"]),
        )
        for item in inspector.get_foreign_keys("test_case_draft")
    }
    draft_unique = {
        item["name"]: tuple(item["column_names"])
        for item in inspector.get_unique_constraints("test_case_draft")
    }
    return {
        "tables": tables,
        "session_columns": session_columns,
        "draft_columns": draft_columns,
        "session_foreign_keys": session_foreign_keys,
        "draft_foreign_keys": draft_foreign_keys,
        "draft_unique": draft_unique,
    }


def test_test_design_migration_upgrades_empty_database_and_db_check(tmp_path):
    app = make_app(tmp_path, "test_design_empty_upgrade.sqlite")
    runner = app.test_cli_runner()

    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output

    with app.app_context():
        snapshot = schema_snapshot()
        assert {
            "test_design_session",
            "test_case_draft",
        } <= snapshot["tables"]
        assert snapshot["session_columns"]["project_id"]["nullable"] is False
        assert snapshot["session_columns"]["version_id"]["nullable"] is False
        assert snapshot["session_columns"]["quality_score"]["nullable"] is False
        assert (
            snapshot["draft_columns"]["accepted_test_case_id"]["nullable"]
            is True
        )
        assert snapshot["session_foreign_keys"][("project_id",)] == (
            "project",
            ("id",),
        )
        assert snapshot["session_foreign_keys"][("version_id",)] == (
            "version",
            ("id",),
        )
        assert snapshot["draft_foreign_keys"][("session_id",)] == (
            "test_design_session",
            ("id",),
        )
        assert snapshot["draft_foreign_keys"][("accepted_test_case_id",)] == (
            "test_case",
            ("id",),
        )
        assert snapshot["draft_unique"]["uq_test_case_draft_accepted_case"] == (
            "accepted_test_case_id",
        )
        assert db.session.execute(
            text("PRAGMA foreign_key_check")
        ).fetchall() == []

    result = runner.invoke(args=["db", "check"])
    assert result.exit_code == 0, result.output


def test_test_design_migration_downgrades_and_reupgrades(tmp_path):
    app = make_app(tmp_path, "test_design_migration_cycle.sqlite")
    runner = app.test_cli_runner()

    result = runner.invoke(args=["db", "upgrade", TEST_DESIGN_REVISION])
    assert result.exit_code == 0, result.output

    result = runner.invoke(args=["db", "downgrade", PREVIOUS_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        assert "test_case_draft" not in tables
        assert "test_design_session" not in tables
        assert db.session.execute(
            text("PRAGMA foreign_key_check")
        ).fetchall() == []

    result = runner.invoke(args=["db", "upgrade", TEST_DESIGN_REVISION])
    assert result.exit_code == 0, result.output
    with app.app_context():
        snapshot = schema_snapshot()
        assert "test_design_session" in snapshot["tables"]
        assert "test_case_draft" in snapshot["tables"]
        assert db.session.execute(
            text("PRAGMA foreign_key_check")
        ).fetchall() == []
