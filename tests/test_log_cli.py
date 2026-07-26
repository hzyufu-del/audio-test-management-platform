import json

from app import create_app
from app.extensions import db
from app.models import LogFile


def test_init_db_seeds_idempotent_mock_log_analysis_metadata(tmp_path):
    database_path = tmp_path / "log_cli_test.sqlite"
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
        assert LogFile.query.count() == 1
        item = LogFile.query.one()
        summary = json.loads(item.analysis_summary)

        assert item.filename == "sample_audio_check.log"
        assert item.analysis_status == "completed"
        assert item.uploaded_by == "demo_tester"
        assert item.file_size_bytes > 0
        assert len(item.sha256) == 64
        assert item.project.code.startswith("MOCK-")
        assert item.version.code.startswith("FW_DEMO_")
        assert "mock" in (item.notes or "").lower()
        assert summary["schema_version"] == 1
        assert summary["total_lines"] == item.total_lines
        assert not hasattr(item, "storage_path")
        assert "real company" not in item.analysis_summary.lower()
