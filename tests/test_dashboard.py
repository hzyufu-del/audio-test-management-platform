from datetime import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import Project, Version


FIXED_NOW = datetime(2026, 7, 11, 12, 0, 0)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "dashboard_route_test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "DASHBOARD_NOW": FIXED_NOW,
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


def test_empty_database_dashboard_is_accessible(client):
    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "测试质量决策页" in page
    assert 'data-scope="project-count">0<' in page
    assert 'data-kpi="execution-total">0<' in page
    assert 'data-kpi="pass-rate">—<' in page
    assert 'data-kpi="fail-rate">—<' in page


def test_dashboard_scope_counts_come_from_database(client, app):
    with app.app_context():
        project = Project(
            name="Mock Dashboard Route Project",
            code="MOCK-DASHBOARD-ROUTE",
            status="active",
        )
        db.session.add(project)
        db.session.commit()

    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-scope="project-count">1<' in page
    assert "Mock Dashboard Route Project" in page


def test_dashboard_rejects_version_outside_selected_project(client, app):
    with app.app_context():
        first_project = Project(
            name="Mock Filter Project A",
            code="MOCK-FILTER-A",
            status="active",
        )
        second_project = Project(
            name="Mock Filter Project B",
            code="MOCK-FILTER-B",
            status="active",
        )
        db.session.add_all([first_project, second_project])
        db.session.flush()
        first_version = Version(
            project_id=first_project.id,
            name="Demo Filter Version A",
            code="FW_DEMO_FILTER_A",
            status="testing",
        )
        second_version = Version(
            project_id=second_project.id,
            name="Demo Filter Version B",
            code="FW_DEMO_FILTER_B",
            status="testing",
        )
        db.session.add_all([first_version, second_version])
        db.session.commit()
        first_project_id = first_project.id
        second_version_id = second_version.id

    response = client.get(
        f"/?project_id={first_project_id}&version_id={second_version_id}",
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所选版本不属于当前项目，已回退为全部版本" in page
    assert 'data-scope="project-count">1<' in page


def test_dashboard_invalid_parameters_fall_back_safely(client):
    response = client.get("/?project_id=bad&version_id=999999&range=90d")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "项目筛选无效，已回退为全部项目" in page
    assert "版本筛选无效，已回退为全部版本" in page
    assert "时间范围无效，已回退为最近 30 天" in page
    assert 'data-range="30d"' in page


def test_dashboard_accepts_supported_range(client):
    response = client.get("/?range=7d")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-range="7d"' in page
    assert "最近 7 天" in page
