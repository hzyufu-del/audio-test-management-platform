import pytest

from app import create_app
from app.extensions import db
from app.models import Project


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
