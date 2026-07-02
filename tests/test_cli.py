from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Project, TestCase as ChecklistTestCase, User


def make_app(tmp_path):
    database_path = tmp_path / "cli_test.sqlite"
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )


def test_init_db_does_not_create_tables_before_migrations(tmp_path):
    app = make_app(tmp_path)

    result = app.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code != 0
    assert "db upgrade" in result.output

    with app.app_context():
        assert inspect(db.engine).get_table_names() == []


def test_init_db_seeds_demo_data_when_schema_exists(tmp_path):
    app = make_app(tmp_path)

    with app.app_context():
        db.create_all()

    result = app.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code == 0
    assert "mock/demo/sample" in result.output

    with app.app_context():
        assert User.query.filter_by(email="demo@example.com").count() == 1
        assert Project.query.filter_by(code="MOCK-AUDIO-01").count() == 1
        assert ChecklistTestCase.query.filter_by(title="Sample playback checklist").count() == 1
