import pytest

from app import create_app
from app.extensions import db
from app.models import Project, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "versions_test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "WTF_CSRF_ENABLED": False,
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
def project(app):
    with app.app_context():
        project = Project(
            name="Mock Version Parent Project",
            code="MOCK-VERSION-PARENT",
            description="Sample parent project for version tests.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()
        return project.id


def test_version_list_page_is_accessible(client):
    response = client.get("/versions/")

    assert response.status_code == 200
    assert "版本管理" in response.get_data(as_text=True)


def test_version_can_be_created(client, app, project):
    response = client.post(
        "/versions/new",
        data={
            "project_id": str(project),
            "name": "Demo Firmware v1.0.0",
            "code": "FW_DEMO_100",
            "description": "Sample version for CRUD testing.",
            "status": "planned",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Demo Firmware v1.0.0" in response.get_data(as_text=True)

    with app.app_context():
        version = Version.query.filter_by(project_id=project, code="FW_DEMO_100").one()
        assert version.name == "Demo Firmware v1.0.0"
        assert version.status == "planned"


def test_version_create_fails_when_project_is_empty(client, app):
    response = client.post(
        "/versions/new",
        data={
            "project_id": "",
            "name": "Demo Firmware Missing Project",
            "code": "FW_DEMO_NO_PROJECT",
            "description": "Sample description should be preserved.",
            "status": "planned",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所属项目不能为空" in page
    assert "Demo Firmware Missing Project" in page
    assert "FW_DEMO_NO_PROJECT" in page

    with app.app_context():
        assert Version.query.count() == 0


def test_version_create_fails_when_name_is_empty(client, app, project):
    response = client.post(
        "/versions/new",
        data={
            "project_id": str(project),
            "name": "",
            "code": "FW_DEMO_NO_NAME",
            "description": "Sample description should be preserved.",
            "status": "planned",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "版本名称不能为空" in page
    assert "FW_DEMO_NO_NAME" in page

    with app.app_context():
        assert Version.query.filter_by(code="FW_DEMO_NO_NAME").count() == 0


def test_version_create_fails_when_code_is_empty(client, app, project):
    response = client.post(
        "/versions/new",
        data={
            "project_id": str(project),
            "name": "Demo Firmware Without Code",
            "code": "",
            "description": "",
            "status": "planned",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "版本编码不能为空" in page
    assert "Demo Firmware Without Code" in page

    with app.app_context():
        assert Version.query.filter_by(name="Demo Firmware Without Code").count() == 0


def test_version_create_fails_when_code_is_duplicated_in_same_project(client, app, project):
    with app.app_context():
        version = Version(
            project_id=project,
            name="Demo Firmware Existing",
            code="FW_DEMO_DUPLICATE",
            description="Sample existing version.",
            status="planned",
        )
        db.session.add(version)
        db.session.commit()

    response = client.post(
        "/versions/new",
        data={
            "project_id": str(project),
            "name": "Demo Firmware Duplicate",
            "code": "FW_DEMO_DUPLICATE",
            "description": "Sample duplicate version.",
            "status": "testing",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "同一项目下版本编码已存在" in page
    assert "Demo Firmware Duplicate" in page

    with app.app_context():
        assert Version.query.filter_by(project_id=project, code="FW_DEMO_DUPLICATE").count() == 1


def test_version_create_fails_when_status_is_invalid(client, app, project):
    response = client.post(
        "/versions/new",
        data={
            "project_id": str(project),
            "name": "Demo Firmware Invalid Status",
            "code": "FW_DEMO_INVALID_STATUS",
            "description": "Sample invalid status version.",
            "status": "paused",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "版本状态只能是 planned、testing、released 或 archived" in page
    assert "Demo Firmware Invalid Status" in page
    assert "FW_DEMO_INVALID_STATUS" in page

    with app.app_context():
        assert Version.query.filter_by(code="FW_DEMO_INVALID_STATUS").count() == 0


def test_version_can_be_edited(client, app, project):
    with app.app_context():
        version = Version(
            project_id=project,
            name="Demo Firmware Before Edit",
            code="FW_DEMO_EDIT",
            description="Sample description before edit.",
            status="planned",
        )
        db.session.add(version)
        db.session.commit()
        version_id = version.id

    response = client.post(
        f"/versions/{version_id}/edit",
        data={
            "project_id": str(project),
            "name": "Demo Firmware After Edit",
            "code": "FW_DEMO_EDITED",
            "description": "Sample description after edit.",
            "status": "released",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Demo Firmware After Edit" in response.get_data(as_text=True)

    with app.app_context():
        updated_version = db.session.get(Version, version_id)
        assert updated_version.name == "Demo Firmware After Edit"
        assert updated_version.code == "FW_DEMO_EDITED"
        assert updated_version.status == "released"


def test_version_can_be_deleted(client, app, project):
    with app.app_context():
        version = Version(
            project_id=project,
            name="Demo Firmware Delete",
            code="FW_DEMO_DELETE",
            description="Sample version to delete.",
            status="planned",
        )
        db.session.add(version)
        db.session.commit()
        version_id = version.id

    response = client.post(f"/versions/{version_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "版本已删除" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Version, version_id) is None
