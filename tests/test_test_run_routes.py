from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import event

from app import create_app
from app.extensions import db
from app.models import (
    Project,
    TestCase as ChecklistTestCase,
    TestExecution as ExecutionRecord,
    TestRun as AutomationTestRun,
    Version,
)
from app.services.junit_import_service import (
    JUnitImportPersistenceError,
    JUnitImportService,
)
from app.services.junit_xml_parser import JUnitXmlParser


SAMPLE_REPORT = (
    Path(__file__).parents[1] / "docs" / "samples" / "junit_demo_results.xml"
)
FIXED_NOW = datetime(2026, 7, 12, 6, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test_run_routes.sqlite"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "JUNIT_IMPORT_NOW": FIXED_NOW,
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


@pytest.fixture()
def target_version(app):
    with app.app_context():
        project = Project(
            name="Mock Web Import Project",
            code="MOCK-WEB-IMPORT",
            status="active",
        )
        db.session.add(project)
        db.session.flush()
        version = Version(
            project_id=project.id,
            name="Demo Web Import Version",
            code="FW_DEMO_WEB_IMPORT",
            status="testing",
        )
        db.session.add(version)
        db.session.flush()
        for code, title, module in (
            ("TC_AUDIO_001", "Sample Audio Playback Checklist", "Audio"),
            ("TC_BT_001", "Sample Bluetooth Reconnect Checklist", "Bluetooth"),
        ):
            db.session.add(
                ChecklistTestCase(
                    version_id=version.id,
                    title=title,
                    code=code,
                    module=module,
                    priority="P1",
                    precondition="Use mock web import state only.",
                    steps=f"Run sample {module.lower()} web import steps.",
                    expected_result="Sample web import result is stable.",
                    status="active",
                )
            )
        db.session.commit()
        return version.id


def upload_data(version_id, content=None, filename="junit_demo_results.xml"):
    content = SAMPLE_REPORT.read_bytes() if content is None else content
    return {
        "version_id": str(version_id),
        "runner": "Demo Web Automation",
        "environment": "Web Import Demo Env",
        "junit_file": (BytesIO(content), filename),
    }


def import_sample(client, version_id, follow_redirects=True):
    return client.post(
        "/test-runs/import",
        data=upload_data(version_id),
        content_type="multipart/form-data",
        follow_redirects=follow_redirects,
    )


def create_imported_run(version_id):
    report = JUnitXmlParser().parse(SAMPLE_REPORT.read_bytes())
    return JUnitImportService().import_report(
        parsed_report=report,
        version_id=version_id,
        runner="Demo Web Automation",
        environment="Web Import Demo Env",
        imported_at=FIXED_NOW,
    )


def test_test_run_list_is_accessible(client):
    response = client.get("/test-runs/")

    assert response.status_code == 200
    assert "自动化测试运行" in response.get_data(as_text=True)


def test_empty_test_run_list_has_friendly_state(client):
    response = client.get("/test-runs/")
    page = response.get_data(as_text=True)

    assert "暂无自动化测试运行" in page
    assert "导入 JUnit XML" in page


def test_test_run_detail_is_accessible(client, app, target_version):
    with app.app_context():
        result = create_imported_run(target_version)
        run_id = result.test_run_id

    response = client.get(f"/test-runs/{run_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "TestRun 详情" in page
    assert "Demo Web Import Version" in page
    assert "TC_AUDIO_001" in page


def test_missing_test_run_returns_404(client):
    response = client.get("/test-runs/999999")

    assert response.status_code == 404


def test_import_page_is_accessible(client, target_version):
    response = client.get("/test-runs/import")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "导入 JUnit XML" in page
    assert "Demo Web Import Version" in page
    assert 'enctype="multipart/form-data"' in page


def test_valid_xml_import_creates_run_and_executions(client, app, target_version):
    response = import_sample(client, target_version)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "JUnit 报告导入成功" in page
    assert "本次创建 4 条执行记录" in page
    with app.app_context():
        assert AutomationTestRun.query.count() == 1
        assert ExecutionRecord.query.count() == 4


def test_import_result_displays_counts_and_links(client, target_version):
    response = import_sample(client, target_version)
    page = response.get_data(as_text=True)

    assert 'data-result-count="total">4<' in page
    assert 'data-result-count="passed">1<' in page
    assert 'data-result-count="failed">2<' in page
    assert 'data-result-count="skipped">1<' in page
    assert "返回 Dashboard" in page
    assert "查看执行记录" in page


def test_duplicate_import_returns_existing_run_without_new_rows(
    client, app, target_version
):
    first = import_sample(client, target_version)
    second = import_sample(client, target_version)
    page = second.get_data(as_text=True)

    assert first.status_code == 200
    assert second.status_code == 200
    assert "该报告已导入" in page
    assert "本次创建 0 条执行记录" in page
    with app.app_context():
        assert AutomationTestRun.query.count() == 1
        assert ExecutionRecord.query.count() == 4


def test_missing_version_is_rejected(client, app):
    response = client.post(
        "/test-runs/import",
        data=upload_data(""),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "请选择目标版本" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


def test_unknown_version_is_rejected(client, app):
    response = client.post(
        "/test-runs/import",
        data=upload_data(999999),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "目标版本不存在" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


def test_missing_file_is_rejected(client, app, target_version):
    response = client.post(
        "/test-runs/import",
        data={"version_id": str(target_version)},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "请选择 JUnit XML 文件" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


def test_empty_file_is_rejected(client, app, target_version):
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, content=b""),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "JUnit XML 文件不能为空" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


def test_non_xml_filename_is_rejected(client, app, target_version):
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, filename="sample_report.txt"),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "仅支持 .xml 文件" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


def test_oversized_file_is_rejected(client, app, target_version):
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, content=b"x" * (5 * 1024 * 1024 + 1)),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "文件超过 5 MiB" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0


@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        (b"<testsuite><testcase></testsuite>", "XML 格式不正确"),
        (
            b'<!DOCTYPE testsuite [<!ENTITY demo "sample">]>'
            b'<testsuite name="demo"><testcase name="&demo;" /></testsuite>',
            "XML 包含不允许的 DTD 或实体",
        ),
    ],
)
def test_parser_errors_are_safe_and_write_nothing(
    client, app, target_version, content, expected_message
):
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, content=content),
        content_type="multipart/form-data",
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert expected_message in page
    assert "<!DOCTYPE" not in page
    assert "<testsuite" not in page
    with app.app_context():
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_unknown_code_displays_safe_matching_summary(client, app, target_version):
    content = b"""<testsuite name="sample-unknown-suite">
      <testcase classname="sample.unknown" name="test_unknown_case">
        <properties>
          <property name="platform_test_case_code" value="TC_SAMPLE_UNKNOWN_001" />
        </properties>
      </testcase>
    </testsuite>"""
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, content=content),
        content_type="multipart/form-data",
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "test_unknown_case" in page
    assert "sample.unknown" in page
    assert "sample-unknown-suite" in page
    assert "TC_SAMPLE_UNKNOWN_001" in page
    assert "目标版本中不存在该用例编号" in page
    with app.app_context():
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_any_unmatched_case_rolls_back_entire_import(client, app, target_version):
    content = b"""<testsuite name="sample-partial-suite">
      <testcase name="test_known"><properties>
        <property name="platform_test_case_code" value="TC_AUDIO_001" />
      </properties></testcase>
      <testcase name="test_missing_code" />
    </testsuite>"""
    response = client.post(
        "/test-runs/import",
        data=upload_data(target_version, content=content),
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "缺少 platform_test_case_code" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_database_import_error_is_friendly_and_writes_nothing(
    client, app, target_version, monkeypatch
):
    def fail_import(*_args, **_kwargs):
        db.session.rollback()
        raise JUnitImportPersistenceError(
            "database_error",
            "Sample database failure.",
        )

    monkeypatch.setattr(JUnitImportService, "import_report", fail_import)
    response = import_sample(client, target_version)

    assert response.status_code == 200
    assert "数据库导入失败，未写入任何执行记录" in response.get_data(as_text=True)
    with app.app_context():
        assert AutomationTestRun.query.count() == 0
        assert ExecutionRecord.query.count() == 0


def test_test_run_list_uses_aggregated_statistics(client, app, target_version):
    with app.app_context():
        create_imported_run(target_version)

    response = client.get("/test-runs/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo Web Import Version" in page
    assert 'data-run-stat="total">4<' in page
    assert 'data-run-stat="passed">1<' in page
    assert 'data-run-stat="failed">2<' in page
    assert 'data-run-stat="skipped">1<' in page


def test_test_run_detail_shows_executions_and_defect_entry(
    client, app, target_version
):
    with app.app_context():
        result = create_imported_run(target_version)
        run_id = result.test_run_id
        failed_id = ExecutionRecord.query.filter_by(result="failed").first().id
        report_hash = db.session.get(AutomationTestRun, run_id).report_hash

    response = client.get(f"/test-runs/{run_id}")
    page = response.get_data(as_text=True)

    assert "test_playback[standard]" not in page
    assert "Sample Audio Playback Checklist" in page
    assert f"/test-executions/{failed_id}" in page
    assert f"/defects/new?test_execution_id={failed_id}" in page
    assert report_hash not in page
    assert report_hash[:12] in page


def test_navigation_and_execution_page_link_to_test_runs(
    client, target_version
):
    nav_page = client.get("/").get_data(as_text=True)
    execution_page = client.get("/test-executions/").get_data(as_text=True)

    assert "/test-runs/" in nav_page
    assert "/test-runs/import" in nav_page
    assert "导入 JUnit XML" in execution_page
    assert "查看 Test Runs" in execution_page


def test_dashboard_counts_imported_executions(client, target_version):
    before = client.get("/").get_data(as_text=True)
    assert 'data-kpi="execution-total">0<' in before

    import_sample(client, target_version)
    after = client.get("/").get_data(as_text=True)

    assert 'data-kpi="execution-total">4<' in after


def test_test_run_list_does_not_query_per_run(client, app, target_version):
    with app.app_context():
        create_imported_run(target_version)
        statements = []

        def collect(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().lower().startswith("select"):
                statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", collect)
        try:
            response = client.get("/test-runs/")
        finally:
            event.remove(db.engine, "before_cursor_execute", collect)

    assert response.status_code == 200
    run_queries = [statement for statement in statements if "test_run" in statement]
    assert len(run_queries) == 1
