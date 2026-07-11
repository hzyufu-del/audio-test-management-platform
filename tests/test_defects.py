import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Defect,
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    Version,
)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "defects_test.sqlite"
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
            name="Mock Defect Parent Project",
            code="MOCK-DEFECT-PARENT",
            description="Sample project for defect tests.",
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
            name="Demo Defect Version",
            code="FW_DEMO_DEFECT",
            description="Sample version for defect tests.",
            status="testing",
        )
        db.session.add(version)
        db.session.commit()
        return version.id


@pytest.fixture()
def test_case(app, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            version_id=version,
            title="Sample Defect Source TestCase",
            code="TC_AUDIO_DEFECT_SOURCE",
            module="Audio",
            priority="P1",
            steps="Run sample defect source steps.",
            expected_result="Sample output remains stable.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        return test_case.id


@pytest.fixture()
def execution(app, test_case):
    with app.app_context():
        test_case_record = db.session.get(ChecklistTestCase, test_case)
        execution = ExecutionRecord(
            result="failed",
            actual_result="Demo audio output is interrupted.",
            tester="Demo Tester",
            environment="Android Demo Env",
            notes="Sample failed execution for defect tests.",
        )
        execution.capture_test_case_snapshot(test_case_record)
        db.session.add(execution)
        db.session.commit()
        return execution.id


def valid_defect_data(execution_id, **overrides):
    data = {
        "test_execution_id": str(execution_id),
        "code": "DEF_DEMO_001",
        "title": "Sample Audio Interruption Defect",
        "description": "Sample issue observed during a demo execution.",
        "component": "Audio",
        "severity": "major",
        "priority": "P1",
        "status": "open",
        "reproduction_steps": "Run the sample playback flow and observe output.",
        "observed_result": "Demo audio output is interrupted.",
        "reporter": "Demo Reporter",
        "assignee": "Sample Assignee",
        "resolution": "",
        "resolution_note": "",
    }
    data.update(overrides)
    return data


def create_defect(client, app, execution_id, **overrides):
    response = client.post(
        "/defects/new",
        data=valid_defect_data(execution_id, **overrides),
        follow_redirects=True,
    )
    assert response.status_code == 200

    code = overrides.get("code", "DEF_DEMO_001")
    with app.app_context():
        defect = Defect.query.filter_by(code=code).one()
        return defect.id


def test_defect_list_page_is_accessible(client):
    response = client.get("/defects/")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "缺陷管理" in page
    assert "新增缺陷" in page


def test_defect_detail_page_is_accessible(client, app, execution):
    defect_id = create_defect(client, app, execution)

    response = client.get(f"/defects/{defect_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "DEF_DEMO_001" in page
    assert "Sample Audio Interruption Defect" in page


def test_defect_can_be_created_from_execution(client, app, execution):
    response = client.post(
        "/defects/new",
        data=valid_defect_data(execution),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "DEF_DEMO_001" in response.get_data(as_text=True)

    with app.app_context():
        defect = Defect.query.filter_by(code="DEF_DEMO_001").one()
        assert defect.test_execution_id == execution
        assert defect.title == "Sample Audio Interruption Defect"
        assert defect.status == "open"


@pytest.mark.parametrize("result", ["passed", "blocked", "skipped"])
def test_defect_create_rejects_non_failed_execution(
    client, app, test_case, result
):
    with app.app_context():
        test_case_record = db.session.get(ChecklistTestCase, test_case)
        execution = ExecutionRecord(
            result=result,
            actual_result="Sample non-failed execution result.",
            tester="Demo Tester",
            environment="Demo Env",
        )
        execution.capture_test_case_snapshot(test_case_record)
        db.session.add(execution)
        db.session.commit()
        execution_id = execution.id

    response = client.post(
        "/defects/new",
        data=valid_defect_data(execution_id),
    )

    assert response.status_code == 200
    assert "只有 failed 执行记录可以创建缺陷" in response.get_data(as_text=True)
    with app.app_context():
        assert Defect.query.count() == 0


def test_defect_create_fails_when_execution_is_empty(client, app):
    response = client.post(
        "/defects/new",
        data=valid_defect_data(""),
    )

    assert response.status_code == 200
    assert "来源执行记录不能为空" in response.get_data(as_text=True)
    with app.app_context():
        assert Defect.query.count() == 0


def test_defect_create_fails_when_execution_does_not_exist(client, app):
    response = client.post(
        "/defects/new",
        data=valid_defect_data("999999"),
    )

    assert response.status_code == 200
    assert "来源执行记录不存在" in response.get_data(as_text=True)
    with app.app_context():
        assert Defect.query.count() == 0


def test_same_execution_can_have_multiple_defects(client, app, execution):
    create_defect(client, app, execution)
    create_defect(
        client,
        app,
        execution,
        code="DEF_DEMO_002",
        title="Sample Secondary Audio Defect",
    )

    with app.app_context():
        assert Defect.query.filter_by(test_execution_id=execution).count() == 2


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("severity", "medium", "严重程度只能是 blocker、critical、major 或 minor"),
        ("priority", "P9", "优先级只能是 P0、P1、P2 或 P3"),
        ("status", "retesting", "缺陷状态只能是 open、fixed、closed 或 rejected"),
    ],
)
def test_defect_create_rejects_invalid_choice(
    client, app, execution, field, value, message
):
    response = client.post(
        "/defects/new",
        data=valid_defect_data(execution, **{field: value}),
    )

    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    with app.app_context():
        assert Defect.query.count() == 0


def test_defect_code_must_be_globally_unique(client, app, execution):
    create_defect(client, app, execution)

    response = client.post(
        "/defects/new",
        data=valid_defect_data(execution, title="Sample Duplicate Code Defect"),
    )

    assert response.status_code == 200
    assert "缺陷编号已存在" in response.get_data(as_text=True)
    with app.app_context():
        assert Defect.query.filter_by(code="DEF_DEMO_001").count() == 1


def test_defect_creation_captures_execution_snapshot(client, app, execution):
    create_defect(client, app, execution)

    with app.app_context():
        source_execution = db.session.get(ExecutionRecord, execution)
        defect = Defect.query.filter_by(code="DEF_DEMO_001").one()
        assert defect.environment_snapshot == "Android Demo Env"
        assert defect.actual_result_snapshot == "Demo audio output is interrupted."
        assert defect.executed_at_snapshot == source_execution.executed_at


def test_defect_can_be_edited_without_changing_identity(client, app, execution):
    defect_id = create_defect(client, app, execution)

    response = client.post(
        f"/defects/{defect_id}/edit",
        data=valid_defect_data(
            execution,
            code="DEF_DEMO_CHANGED",
            title="Sample Edited Audio Defect",
            severity="critical",
            priority="P0",
            status="fixed",
            resolution="fixed",
            resolution_note="Sample resolution note.",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Sample Edited Audio Defect" in response.get_data(as_text=True)

    with app.app_context():
        defect = db.session.get(Defect, defect_id)
        assert defect.code == "DEF_DEMO_001"
        assert defect.test_execution_id == execution
        assert defect.title == "Sample Edited Audio Defect"
        assert defect.status == "fixed"


def test_defect_edit_does_not_refresh_execution_snapshot(client, app, execution):
    defect_id = create_defect(client, app, execution)

    with app.app_context():
        source_execution = db.session.get(ExecutionRecord, execution)
        source_execution.environment = "Changed Live Demo Env"
        source_execution.actual_result = "Changed live actual result."
        db.session.commit()

    client.post(
        f"/defects/{defect_id}/edit",
        data=valid_defect_data(execution, title="Sample Snapshot Safe Edit"),
        follow_redirects=True,
    )

    with app.app_context():
        defect = db.session.get(Defect, defect_id)
        assert defect.environment_snapshot == "Android Demo Env"
        assert defect.actual_result_snapshot == "Demo audio output is interrupted."


def test_defect_can_be_deleted(client, app, execution):
    defect_id = create_defect(client, app, execution)

    response = client.post(f"/defects/{defect_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "缺陷已删除" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Defect, defect_id) is None


def test_execution_with_defects_cannot_be_deleted(client, app, execution):
    defect_id = create_defect(client, app, execution)

    response = client.post(
        f"/test-executions/{execution}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "该执行记录下已有缺陷，不能直接删除" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(ExecutionRecord, execution) is not None
        assert db.session.get(Defect, defect_id) is not None
