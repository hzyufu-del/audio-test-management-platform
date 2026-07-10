import pytest

from app import create_app
from app.extensions import db
from app.models import Project, TestCase as ChecklistTestCase, TestExecution as ExecutionRecord, Version


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test_executions_test.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
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
            name="Mock Execution Parent Project",
            code="MOCK-EXECUTION-PARENT",
            description="Sample parent project for execution tests.",
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
            name="Demo Firmware Execution Version",
            code="FW_DEMO_EXECUTION",
            description="Sample parent version for execution tests.",
            status="testing",
        )
        db.session.add(version)
        db.session.commit()
        return version.id


@pytest.fixture()
def test_case(app, project, version):
    with app.app_context():
        test_case = ChecklistTestCase(
            project_id=project,
            version_id=version,
            title="Sample Execution TestCase",
            code="TC_AUDIO_EXECUTION",
            module="Audio",
            priority="P1",
            steps="Run sample execution steps.",
            expected_result="Sample execution expected result.",
            status="active",
        )
        db.session.add(test_case)
        db.session.commit()
        return test_case.id


def valid_execution_data(test_case_id, **overrides):
    data = {
        "test_case_id": str(test_case_id),
        "result": "passed",
        "actual_result": "Demo actual result is recorded.",
        "tester": "Demo Tester",
        "environment": "Android Demo Env",
        "executed_at": "",
        "notes": "Sample execution notes.",
    }
    data.update(overrides)
    return data


def create_execution(app, test_case_id, **overrides):
    with app.app_context():
        test_case = db.session.get(ChecklistTestCase, test_case_id)
        execution = ExecutionRecord(
            test_case_id=test_case.id,
            version_id=test_case.version_id,
            result=overrides.get("result", "passed"),
            actual_result=overrides.get("actual_result", "Demo actual result is recorded."),
            tester=overrides.get("tester", "Demo Tester"),
            environment=overrides.get("environment", "Android Demo Env"),
            notes=overrides.get("notes", "Sample execution notes."),
        )
        db.session.add(execution)
        db.session.commit()
        return execution.id


def test_execution_list_page_is_accessible(client):
    response = client.get("/test-executions/")

    assert response.status_code == 200
    assert "执行记录管理" in response.get_data(as_text=True)


def test_execution_detail_page_is_accessible(client, app, test_case):
    execution_id = create_execution(app, test_case)

    response = client.get(f"/test-executions/{execution_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo Tester" in page
    assert "TC_AUDIO_EXECUTION" in page


def test_execution_can_be_created(client, app, test_case):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data(test_case),
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo Tester" in page
    assert "passed" in page

    with app.app_context():
        execution = ExecutionRecord.query.filter_by(test_case_id=test_case).one()
        assert execution.result == "passed"
        assert execution.actual_result == "Demo actual result is recorded."
        assert execution.executed_at is not None


def test_execution_create_fails_when_test_case_is_empty(client, app):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data("", result="passed"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所属用例不能为空" in page

    with app.app_context():
        assert ExecutionRecord.query.count() == 0


def test_execution_create_fails_when_test_case_does_not_exist(client, app):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data("99999", result="passed"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "所属用例不存在" in page

    with app.app_context():
        assert ExecutionRecord.query.count() == 0


def test_execution_create_fails_when_result_is_empty(client, app, test_case):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data(test_case, result=""),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "执行结果不能为空" in page

    with app.app_context():
        assert ExecutionRecord.query.count() == 0


def test_execution_create_fails_when_result_is_invalid(client, app, test_case):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data(test_case, result="unknown"),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "执行结果只能是 passed、failed、blocked 或 skipped" in page

    with app.app_context():
        assert ExecutionRecord.query.count() == 0


def test_execution_create_fails_when_failed_actual_result_is_empty(client, app, test_case):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data(test_case, result="failed", actual_result=""),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "失败结果必须填写实际结果" in page

    with app.app_context():
        assert ExecutionRecord.query.count() == 0


def test_execution_create_allows_passed_actual_result_empty(client, app, test_case):
    response = client.post(
        "/test-executions/new",
        data=valid_execution_data(test_case, result="passed", actual_result=""),
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        execution = ExecutionRecord.query.filter_by(test_case_id=test_case).one()
        assert execution.result == "passed"
        assert execution.actual_result == ""


def test_execution_can_be_edited(client, app, test_case):
    execution_id = create_execution(app, test_case)

    response = client.post(
        f"/test-executions/{execution_id}/edit",
        data=valid_execution_data(
            test_case,
            result="blocked",
            actual_result="Demo blocked actual result.",
            tester="Sample Tester",
            environment="Firmware Demo Env",
            notes="Sample edited notes.",
        ),
        follow_redirects=True,
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Sample Tester" in page
    assert "blocked" in page

    with app.app_context():
        execution = db.session.get(ExecutionRecord, execution_id)
        assert execution.result == "blocked"
        assert execution.tester == "Sample Tester"
        assert execution.environment == "Firmware Demo Env"


def test_execution_edit_failure_does_not_pollute_existing_record(client, app, test_case):
    execution_id = create_execution(
        app,
        test_case,
        result="passed",
        actual_result="Original sample result.",
        tester="Demo Tester",
    )

    response = client.post(
        f"/test-executions/{execution_id}/edit",
        data=valid_execution_data(
            test_case,
            result="failed",
            actual_result="",
            tester="Sample Invalid Tester",
        ),
    )

    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "失败结果必须填写实际结果" in page
    assert "Sample Invalid Tester" in page

    with app.app_context():
        execution = db.session.get(ExecutionRecord, execution_id)
        assert execution.result == "passed"
        assert execution.actual_result == "Original sample result."
        assert execution.tester == "Demo Tester"


def test_execution_can_be_deleted(client, app, test_case):
    execution_id = create_execution(app, test_case)

    response = client.post(f"/test-executions/{execution_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "执行记录已删除" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(ExecutionRecord, execution_id) is None


def test_test_case_delete_with_executions_fails_gracefully(client, app, test_case):
    execution_id = create_execution(app, test_case)

    response = client.post(f"/test-cases/{test_case}/delete", follow_redirects=True)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "该用例下已有执行记录，不能直接删除" in page

    with app.app_context():
        assert db.session.get(ChecklistTestCase, test_case) is not None
        assert db.session.get(ExecutionRecord, execution_id) is not None
