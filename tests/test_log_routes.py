import json
from io import BytesIO

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.extensions import db
from app.models import LogFile, Project, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "log_routes_test.sqlite"
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


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def log_targets(app):
    with app.app_context():
        project = Project(
            name="Mock Log Route Project",
            code="MOCK-LOG-ROUTE",
            status="active",
        )
        other_project = Project(
            name="Sample Other Log Project",
            code="SAMPLE-OTHER-LOG",
            status="active",
        )
        db.session.add_all((project, other_project))
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo Log Firmware",
            code="FW_DEMO_LOG",
            status="testing",
        )
        other_version = Version(
            project_id=other_project.id,
            name="Sample Other Firmware",
            code="FW_SAMPLE_OTHER_LOG",
            status="testing",
        )
        db.session.add_all((version, other_version))
        db.session.commit()
        return {
            "project_id": project.id,
            "version_id": version.id,
            "other_project_id": other_project.id,
            "other_version_id": other_version.id,
        }


def upload_data(
    project_id,
    version_id="",
    content=b"INFO sample audio connection\nERROR protocol timeout",
    filename="sample.log",
    notes="Mock upload route test.",
):
    return {
        "project_id": str(project_id),
        "version_id": str(version_id),
        "notes": notes,
        "log_file": (BytesIO(content), filename),
    }


def upload_log(client, data, follow_redirects=False):
    return client.post(
        "/logs/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=follow_redirects,
    )


def add_log_record(project_id, version_id=None, filename="database_only.log"):
    summary = {
        "schema_version": 1,
        "total_lines": 2,
        "levels": {
            "critical": 0,
            "error": 1,
            "warning": 1,
            "info": 0,
        },
        "risk_level": "high",
        "domains": {
            "connection": 0,
            "power": 0,
            "battery": 1,
            "audio": 1,
            "protocol": 0,
        },
        "findings": [
            {
                "line_number": 2,
                "level": "error",
                "domains": ["audio"],
                "snippet": "ERROR sample audio failure",
            }
        ],
        "findings_truncated": False,
    }
    item = LogFile(
        project_id=project_id,
        version_id=version_id,
        filename=filename,
        file_size_bytes=64,
        sha256="b" * 64,
        analysis_status="completed",
        risk_level="high",
        total_lines=2,
        critical_count=0,
        error_count=1,
        warning_count=1,
        info_count=0,
        analysis_summary=json.dumps(summary),
        uploaded_by="demo_tester",
        notes="Mock database-backed log.",
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def test_log_list_reads_database_rows(client, app, log_targets):
    empty_page = client.get("/logs/").get_data(as_text=True)
    assert "database_only.log" not in empty_page

    with app.app_context():
        add_log_record(
            log_targets["project_id"],
            log_targets["version_id"],
        )

    response = client.get("/logs/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "database_only.log" in page
    assert "Mock Log Route Project" in page
    assert "Demo Log Firmware" in page
    assert 'data-log-risk="high"' in page
    assert 'data-log-errors="1"' in page
    assert 'data-log-warnings="1"' in page


def test_upload_page_is_accessible(client, log_targets):
    response = client.get("/logs/upload")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'enctype="multipart/form-data"' in page
    assert "Mock Log Route Project" in page
    assert "Demo Log Firmware" in page
    assert "Original log content is never stored." in page


def test_successful_upload_redirects_to_detail_and_stores_summary_only(
    client,
    app,
    log_targets,
):
    private_info = "INFO private-token-that-must-not-be-stored"
    finding = "ERROR audio protocol sample failure"
    response = upload_log(
        client,
        upload_data(
            log_targets["project_id"],
            log_targets["version_id"],
            content=f"{private_info}\n{finding}".encode(),
            filename="../../unsafe demo.LOG",
        ),
    )

    assert response.status_code == 302
    assert "/logs/" in response.headers["Location"]

    with app.app_context():
        item = LogFile.query.one()
        item_id = item.id
        assert item.filename == "unsafe_demo.LOG"
        assert item.project_id == log_targets["project_id"]
        assert item.version_id == log_targets["version_id"]
        assert item.analysis_status == "completed"
        assert item.risk_level == "high"
        assert item.total_lines == 2
        assert item.error_count == 1
        assert item.uploaded_by == "anonymous_demo"
        assert private_info not in item.analysis_summary
        assert finding in item.analysis_summary
        assert not hasattr(item, "storage_path")
        assert not hasattr(item, "raw_content")

    detail = client.get(f"/logs/{item_id}").get_data(as_text=True)
    assert "unsafe_demo.LOG" in detail
    assert finding in detail
    assert "Original log content is never stored." in detail


def test_version_is_optional(client, app, log_targets):
    response = upload_log(
        client,
        upload_data(log_targets["project_id"], version_id=""),
    )

    assert response.status_code == 302
    with app.app_context():
        assert LogFile.query.one().version_id is None


def test_upload_requires_file(client, app, log_targets):
    response = client.post(
        "/logs/upload",
        data={
            "project_id": str(log_targets["project_id"]),
            "version_id": "",
            "notes": "Mock missing-file request.",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Select a .log or .txt file." in response.get_data(as_text=True)
    with app.app_context():
        assert LogFile.query.count() == 0


@pytest.mark.parametrize(
    ("project_id", "version_id", "expected_message"),
    (
        ("", "", "Project is required."),
        ("999999", "", "Selected Project does not exist."),
        ("project", "", "Project is required."),
        ("PROJECT", "", "Project is required."),
    ),
)
def test_upload_rejects_missing_or_unknown_project(
    client,
    app,
    project_id,
    version_id,
    expected_message,
):
    response = upload_log(
        client,
        upload_data(project_id, version_id=version_id),
    )

    assert response.status_code == 200
    assert expected_message in response.get_data(as_text=True)
    with app.app_context():
        assert LogFile.query.count() == 0


def test_upload_rejects_unknown_version(client, app, log_targets):
    response = upload_log(
        client,
        upload_data(log_targets["project_id"], version_id="999999"),
    )

    assert response.status_code == 200
    assert "Selected Version does not exist." in response.get_data(
        as_text=True
    )
    with app.app_context():
        assert LogFile.query.count() == 0


def test_upload_rejects_version_from_another_project(
    client,
    app,
    log_targets,
):
    response = upload_log(
        client,
        upload_data(
            log_targets["project_id"],
            version_id=log_targets["other_version_id"],
        ),
    )

    assert response.status_code == 200
    assert (
        "Selected Version does not belong to the selected Project."
        in response.get_data(as_text=True)
    )
    with app.app_context():
        assert LogFile.query.count() == 0


@pytest.mark.parametrize(
    ("filename", "content", "expected_message"),
    (
        ("sample.xml", b"INFO sample", "Only .log and .txt files"),
        ("empty.log", b"", "The log file is empty."),
        ("binary.log", b"INFO\x00binary", "appears to contain binary"),
        ("invalid.log", b"\xff\xfe\xfa", "valid UTF-8"),
    ),
)
def test_upload_rejects_invalid_log_content(
    client,
    app,
    log_targets,
    filename,
    content,
    expected_message,
):
    response = upload_log(
        client,
        upload_data(
            log_targets["project_id"],
            filename=filename,
            content=content,
        ),
    )

    assert response.status_code == 200
    assert expected_message in response.get_data(as_text=True)
    with app.app_context():
        assert LogFile.query.count() == 0


def test_upload_rejects_duplicate_hash_within_project(
    client,
    app,
    log_targets,
):
    data = upload_data(log_targets["project_id"])
    first = upload_log(client, data)
    assert first.status_code == 302

    duplicate = upload_log(
        client,
        upload_data(
            log_targets["project_id"],
            filename="renamed.txt",
        ),
    )

    assert duplicate.status_code == 200
    assert (
        "already been analyzed for the selected Project"
        in duplicate.get_data(as_text=True)
    )
    with app.app_context():
        assert LogFile.query.count() == 1


def test_database_failure_rolls_back_without_partial_record(
    client,
    app,
    log_targets,
    monkeypatch,
):
    def fail_commit():
        raise OperationalError(
            "INSERT INTO log_file",
            {},
            RuntimeError("sample database failure"),
        )

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = upload_log(
        client,
        upload_data(log_targets["project_id"]),
    )

    assert response.status_code == 200
    assert (
        "Log analysis could not be saved. No data was written."
        in response.get_data(as_text=True)
    )
    with app.app_context():
        assert LogFile.query.count() == 0


def test_non_duplicate_integrity_failure_uses_generic_database_error(
    client,
    app,
    log_targets,
    monkeypatch,
):
    def fail_commit():
        raise IntegrityError(
            "INSERT INTO log_file",
            {},
            RuntimeError("sample non-duplicate constraint failure"),
        )

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = upload_log(
        client,
        upload_data(log_targets["project_id"]),
    )

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Log analysis could not be saved. No data was written." in page
    assert "already been analyzed" not in page
    with app.app_context():
        assert LogFile.query.count() == 0


def test_missing_log_detail_returns_404(client):
    response = client.get("/logs/999999")

    assert response.status_code == 404


def test_log_snippet_is_escaped_by_jinja(client, app, log_targets):
    content = b'ERROR audio <script>alert("sample")</script>'
    response = upload_log(
        client,
        upload_data(log_targets["project_id"], content=content),
    )
    assert response.status_code == 302

    with app.app_context():
        item_id = LogFile.query.one().id

    page = client.get(f"/logs/{item_id}").get_data(as_text=True)

    assert "&lt;script&gt;" in page
    assert "<script>" not in page
