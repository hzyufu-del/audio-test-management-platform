import pytest

from app import create_app
from app.extensions import db
from app.models import Project, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "projects_test.sqlite"
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


def test_project_list_page_is_accessible(client):
    response = client.get("/projects/")

    assert response.status_code == 200
    assert "项目管理" in response.get_data(as_text=True)


def test_project_can_be_created(client, app):
    response = client.post(
        "/projects/new",
        data={
            "name": "Mock Project Alpha",
            "code": "MOCK-PROJECT-ALPHA",
            "description": "Sample project for CRUD testing.",
            "status": "active",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Mock Project Alpha" in response.get_data(as_text=True)

    with app.app_context():
        project = Project.query.filter_by(code="MOCK-PROJECT-ALPHA").one()
        assert project.name == "Mock Project Alpha"
        assert project.status == "active"


def test_project_create_fails_when_name_is_empty(client, app):
    response = client.post(
        "/projects/new",
        data={
            "name": "",
            "code": "MOCK-PROJECT-NO-NAME",
            "description": "Sample description should be preserved.",
            "status": "active",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目名称不能为空" in page
    assert "MOCK-PROJECT-NO-NAME" in page
    assert "Sample description should be preserved." in page

    with app.app_context():
        assert Project.query.filter_by(code="MOCK-PROJECT-NO-NAME").count() == 0


def test_project_create_fails_when_code_is_empty(client, app):
    response = client.post(
        "/projects/new",
        data={
            "name": "Mock Project Without Code",
            "code": "",
            "description": "",
            "status": "active",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目编码不能为空" in page
    assert "Mock Project Without Code" in page

    with app.app_context():
        assert Project.query.filter_by(name="Mock Project Without Code").count() == 0


def test_project_create_fails_when_code_is_duplicated(client, app):
    with app.app_context():
        project = Project(
            name="Mock Existing Project",
            code="MOCK-PROJECT-DUPLICATE",
            description="Demo existing project.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()

    response = client.post(
        "/projects/new",
        data={
            "name": "Mock Duplicate Project",
            "code": "MOCK-PROJECT-DUPLICATE",
            "description": "Sample duplicate description.",
            "status": "active",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目编码已存在" in page
    assert "Mock Duplicate Project" in page

    with app.app_context():
        assert Project.query.filter_by(code="MOCK-PROJECT-DUPLICATE").count() == 1


def test_project_create_fails_when_status_is_invalid(client, app):
    response = client.post(
        "/projects/new",
        data={
            "name": "Mock Project Invalid Status",
            "code": "MOCK-PROJECT-INVALID-STATUS",
            "description": "Demo invalid status description.",
            "status": "paused",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目状态只能是 active 或 archived" in page
    assert "Mock Project Invalid Status" in page
    assert "MOCK-PROJECT-INVALID-STATUS" in page

    with app.app_context():
        assert Project.query.filter_by(code="MOCK-PROJECT-INVALID-STATUS").count() == 0


def test_project_can_be_edited(client, app):
    with app.app_context():
        project = Project(
            name="Mock Project Before Edit",
            code="MOCK-PROJECT-EDIT",
            description="Demo description before edit.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client.post(
        f"/projects/{project_id}/edit",
        data={
            "name": "Mock Project After Edit",
            "code": "MOCK-PROJECT-EDITED",
            "description": "Sample description after edit.",
            "status": "archived",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Mock Project After Edit" in response.get_data(as_text=True)

    with app.app_context():
        updated_project = db.session.get(Project, project_id)
        assert updated_project.name == "Mock Project After Edit"
        assert updated_project.code == "MOCK-PROJECT-EDITED"
        assert updated_project.status == "archived"


def test_project_edit_failure_preserves_user_input(client, app):
    with app.app_context():
        project = Project(
            name="Mock Project Original",
            code="MOCK-PROJECT-ORIGINAL",
            description="Demo original description.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client.post(
        f"/projects/{project_id}/edit",
        data={
            "name": "Mock Project Invalid Edit",
            "code": "MOCK-PROJECT-INVALID-EDIT",
            "description": "Sample attempted edit description.",
            "status": "paused",
        },
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目状态只能是 active 或 archived" in page
    assert "Mock Project Invalid Edit" in page
    assert "MOCK-PROJECT-INVALID-EDIT" in page
    assert "Sample attempted edit description." in page

    with app.app_context():
        unchanged_project = db.session.get(Project, project_id)
        assert unchanged_project.name == "Mock Project Original"
        assert unchanged_project.code == "MOCK-PROJECT-ORIGINAL"
        assert unchanged_project.status == "active"


def test_project_can_be_deleted(client, app):
    with app.app_context():
        project = Project(
            name="Mock Project Delete",
            code="MOCK-PROJECT-DELETE",
            description="Demo project to delete.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client.post(f"/projects/{project_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "项目已删除" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Project, project_id) is None


def test_project_delete_with_versions_fails_gracefully(client, app):
    with app.app_context():
        project = Project(
            name="Mock Project With Version",
            code="MOCK-PROJECT-WITH-VERSION",
            description="Demo project with related version.",
            status="active",
        )
        db.session.add(project)
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo Firmware Linked Version",
            code="FW_DEMO_LINKED",
            description="Sample linked version.",
            status="planned",
        )
        db.session.add(version)
        db.session.commit()
        project_id = project.id
        version_id = version.id

    response = client.post(f"/projects/{project_id}/delete", follow_redirects=True)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "该项目下已有版本，不能直接删除" in page

    with app.app_context():
        assert db.session.get(Project, project_id) is not None
        assert db.session.get(Version, version_id) is not None
