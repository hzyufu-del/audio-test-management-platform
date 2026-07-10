import pytest

from app import create_app
from app.extensions import db
from app.models import Project, TestCase as ChecklistTestCase, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test_cases_test.sqlite"
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
            name="Mock TestCase Parent Project",
            code="MOCK-TESTCASE-PARENT",
            description="Sample parent project for testcase tests.",
            status="active",
        )
        db.session.add(project)
        db.session.commit()
        return project.id


@pytest.fixture()
def version(app, project):
    with app.app_context():
        version = Version(
            project_id=project,
            name="Demo Firmware TestCase Version",
            code="FW_DEMO_TESTCASE",
            description="Sample parent version for testcase tests.",
            status="testing",
        )
        db.session.add(version)
        db.session.commit()
        return version.id


@pytest.fixture()
def another_version(app, project):
    with app.app_context():
        version = Version(
            project_id=project,
            name="Demo Firmware Alternate TestCase Version",
            code="FW_DEMO_TESTCASE_ALT",
            description="Sample alternate version for testcase tests.",
            status="testing",
        )
        db.session.add(version)
        db.session.commit()
        return version.id


def valid_test_case_data(version_id, **overrides):
    data = {
        "version_id": str(version_id),
        "title": "Sample Audio Playback Checklist",
        "code": "TC_AUDIO_001",
        "module": "Audio",
        "priority": "P1",
        "precondition": "Use a mock audio device state.",
        "steps": "Open demo playback flow and check sample output.",
        "expected_result": "Sample playback result is recorded.",
        "status": "active",
    }
    data.update(overrides)
    return data


def test_test_case_list_page_is_accessible(client):
    response = client.get("/test-cases/")

    assert response.status_code == 200
    assert "测试用例管理" in response.get_data(as_text=True)


def test_test_case_can_be_created(client, app, version):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Sample Audio Playback Checklist" in response.get_data(as_text=True)

    with app.app_context():
        test_case = ChecklistTestCase.query.filter_by(version_id=version, code="TC_AUDIO_001").one()
        assert test_case.title == "Sample Audio Playback Checklist"
        assert test_case.priority == "P1"
        assert test_case.status == "active"


def test_test_case_detail_page_is_accessible(client, app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample TestCase Detail",
            code="TC_AUDIO_DETAIL",
            module="Audio",
            priority="P1",
            steps="Run sample detail steps.",
            expected_result="Sample detail result is recorded.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        test_case_id = test_case.id

    response = client.get(f"/test-cases/{test_case_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Sample TestCase Detail" in page
    assert "TC_AUDIO_DETAIL" in page


def test_test_case_create_fails_when_title_is_empty(client, app, version):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version, title="", code="TC_AUDIO_NO_TITLE"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "用例标题不能为空" in page
    assert "TC_AUDIO_NO_TITLE" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_NO_TITLE").count() == 0


def test_test_case_create_fails_when_code_is_empty(client, app, version):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version, title="Sample TestCase Without Code", code=""),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "用例编号不能为空" in page
    assert "Sample TestCase Without Code" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(title="Sample TestCase Without Code").count() == 0


def test_test_case_create_fails_when_version_is_empty(client, app):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data("", code="TC_AUDIO_NO_VERSION"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所属版本不能为空" in page
    assert "TC_AUDIO_NO_VERSION" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_NO_VERSION").count() == 0


def test_test_case_create_fails_when_version_does_not_exist(client, app):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data("99999", code="TC_AUDIO_BAD_VERSION"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所属版本不存在" in page
    assert "TC_AUDIO_BAD_VERSION" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_BAD_VERSION").count() == 0


def test_test_case_create_fails_when_code_is_duplicated_in_same_version(client, app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample Existing TestCase",
            code="TC_AUDIO_DUPLICATE",
            module="Audio",
            priority="P2",
            steps="Run sample steps.",
            expected_result="Sample expected result.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()

    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version, code="TC_AUDIO_DUPLICATE", title="Sample Duplicate TestCase"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "同一版本下用例编号已存在" in page
    assert "Sample Duplicate TestCase" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(version_id=version, code="TC_AUDIO_DUPLICATE").count() == 1


def test_test_case_create_allows_same_code_in_different_versions(client, app, version, another_version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample Existing Shared Code TestCase",
            code="TC_AUDIO_SHARED",
            module="Audio",
            priority="P2",
            steps="Run sample steps.",
            expected_result="Sample expected result.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()

    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(
            another_version,
            code="TC_AUDIO_SHARED",
            title="Sample Shared Code In Another Version",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Sample Shared Code In Another Version" in response.get_data(as_text=True)

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_SHARED").count() == 2


def test_test_case_create_fails_when_priority_is_invalid(client, app, version):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version, code="TC_AUDIO_BAD_PRIORITY", priority="P9"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "优先级只能是 P0、P1、P2 或 P3" in page
    assert "TC_AUDIO_BAD_PRIORITY" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_BAD_PRIORITY").count() == 0


def test_test_case_create_fails_when_status_is_invalid(client, app, version):
    response = client.post(
        "/test-cases/new",
        data=valid_test_case_data(version, code="TC_AUDIO_BAD_STATUS", status="paused"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "用例状态只能是 draft、active 或 archived" in page
    assert "TC_AUDIO_BAD_STATUS" in page

    with app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_AUDIO_BAD_STATUS").count() == 0


def test_test_case_can_be_edited(client, app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample TestCase Before Edit",
            code="TC_AUDIO_EDIT",
            module="Audio",
            priority="P2",
            steps="Run sample steps before edit.",
            expected_result="Sample expected result before edit.",
            status="draft",
        )
        db.session.add(test_case)
        db.session.commit()
        test_case_id = test_case.id

    response = client.post(
        f"/test-cases/{test_case_id}/edit",
        data=valid_test_case_data(
            version,
            title="Sample TestCase After Edit",
            code="TC_AUDIO_EDITED",
            module="Bluetooth",
            priority="P0",
            status="archived",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Sample TestCase After Edit" in response.get_data(as_text=True)

    with app.app_context():
        updated_test_case = db.session.get(ChecklistTestCase, test_case_id)
        assert updated_test_case.title == "Sample TestCase After Edit"
        assert updated_test_case.code == "TC_AUDIO_EDITED"
        assert updated_test_case.module == "Bluetooth"
        assert updated_test_case.priority == "P0"
        assert updated_test_case.status == "archived"


def test_test_case_edit_failure_does_not_pollute_existing_record(client, app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample TestCase Original",
            code="TC_AUDIO_ORIGINAL",
            module="Audio",
            priority="P2",
            steps="Run original sample steps.",
            expected_result="Original sample expected result.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        test_case_id = test_case.id

    response = client.post(
        f"/test-cases/{test_case_id}/edit",
        data=valid_test_case_data(
            version,
            title="Sample TestCase Invalid Edit",
            code="TC_AUDIO_INVALID_EDIT",
            priority="P9",
            status="active",
        ),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "优先级只能是 P0、P1、P2 或 P3" in page
    assert "Sample TestCase Invalid Edit" in page
    assert "TC_AUDIO_INVALID_EDIT" in page

    with app.app_context():
        unchanged_test_case = db.session.get(ChecklistTestCase, test_case_id)
        assert unchanged_test_case.title == "Sample TestCase Original"
        assert unchanged_test_case.code == "TC_AUDIO_ORIGINAL"
        assert unchanged_test_case.priority == "P2"


def test_test_case_can_be_deleted(client, app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            project_id=db.session.get(Version, version).project_id,
            title="Sample TestCase Delete",
            code="TC_AUDIO_DELETE",
            module="Audio",
            priority="P2",
            steps="Run sample delete steps.",
            expected_result="Sample delete expected result.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        test_case_id = test_case.id

    response = client.post(f"/test-cases/{test_case_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "用例已删除" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(ChecklistTestCase, test_case_id) is None
