import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import LogFile, Project


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "log_model_test.sqlite"
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


def build_log(project_id, sha256, filename="sample.log"):
    return LogFile(
        project_id=project_id,
        filename=filename,
        file_size_bytes=42,
        sha256=sha256,
        analysis_status="completed",
        risk_level="low",
        total_lines=1,
        critical_count=0,
        error_count=0,
        warning_count=0,
        info_count=1,
        analysis_summary='{"schema_version":1}',
        uploaded_by="demo_tester",
        notes="Mock log analysis metadata.",
    )


def test_log_file_schema_stores_only_metadata_and_bounded_summary(app):
    with app.app_context():
        inspector = inspect(db.engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("log_file")
        }
        unique_constraints = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("log_file")
        }
        foreign_keys = {
            tuple(foreign_key["constrained_columns"]): (
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys("log_file")
        }

    assert {
        "id",
        "project_id",
        "version_id",
        "filename",
        "file_size_bytes",
        "sha256",
        "analysis_status",
        "risk_level",
        "total_lines",
        "critical_count",
        "error_count",
        "warning_count",
        "info_count",
        "analysis_summary",
        "uploaded_by",
        "notes",
        "uploaded_at",
    } == set(columns)
    assert columns["project_id"]["nullable"] is False
    assert columns["version_id"]["nullable"] is True
    assert columns["analysis_summary"]["nullable"] is False
    assert columns["uploaded_by"]["nullable"] is False
    assert "storage_path" not in columns
    assert "raw_content" not in columns
    assert "content" not in columns
    assert unique_constraints["uq_log_file_project_sha256"] == (
        "project_id",
        "sha256",
    )
    assert foreign_keys[("project_id",)] == ("project", ("id",))
    assert foreign_keys[("version_id",)] == ("version", ("id",))


def test_duplicate_hash_is_rejected_within_project_only(app):
    digest = "a" * 64

    with app.app_context():
        first_project = Project(
            name="Mock Log Project One",
            code="MOCK-LOG-ONE",
            status="active",
        )
        second_project = Project(
            name="Mock Log Project Two",
            code="MOCK-LOG-TWO",
            status="active",
        )
        db.session.add_all((first_project, second_project))
        db.session.flush()
        db.session.add(build_log(first_project.id, digest))
        db.session.commit()

        db.session.add(build_log(first_project.id, digest, "duplicate.txt"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        db.session.add(build_log(second_project.id, digest, "allowed.txt"))
        db.session.commit()

        assert LogFile.query.filter_by(sha256=digest).count() == 2
