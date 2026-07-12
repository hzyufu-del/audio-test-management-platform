from collections import Counter

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import Project, TestExecution, TestRun, Version
from app.services.junit_import_service import (
    JUnitImportPersistenceError,
    JUnitImportService,
    JUnitImportValidationError,
)
from app.services.junit_xml_parser import JUnitParseError, JUnitXmlParser, ParserConfig


bp = Blueprint("test_runs", __name__, url_prefix="/test-runs")
PARSER_ERROR_MESSAGES = {
    "file_too_large": "JUnit XML 文件超过 5 MiB 限制。",
    "malformed_xml": "JUnit XML 格式不正确。",
    "unsafe_xml": "JUnit XML 包含不允许的 DTD 或实体。",
    "unsupported_root": "仅支持 testsuite 或 testsuites 根节点。",
    "empty_report": "JUnit XML 中没有可导入的 testcase。",
    "missing_testcase_name": "JUnit XML 中存在缺少名称的 testcase。",
    "conflicting_outcomes": "JUnit XML 中存在冲突的测试结果节点。",
    "too_many_testcases": "JUnit XML 中的 testcase 数量超过限制。",
    "suite_depth_exceeded": "JUnit XML 的 testsuite 嵌套层级超过限制。",
    "property_limit_exceeded": "JUnit XML 中的 property 超过安全限制。",
    "invalid_duration": "JUnit XML 中存在非法的执行耗时。",
}
VALIDATION_REASON_MESSAGES = {
    "missing_test_case_code": "缺少 platform_test_case_code",
    "test_case_not_found": "目标版本中不存在该用例编号",
    "duplicate_external_case_key": "报告中存在重复的 external_case_key",
    "mixed_timestamp_awareness": "报告中的时间时区格式不一致",
}


@bp.get("/")
def index():
    stats = (
        db.select(
            TestExecution.test_run_id.label("test_run_id"),
            func.count(TestExecution.id).label("total"),
            func.sum(
                case((TestExecution.result == "passed", 1), else_=0)
            ).label("passed"),
            func.sum(
                case((TestExecution.result == "failed", 1), else_=0)
            ).label("failed"),
            func.sum(
                case((TestExecution.result == "skipped", 1), else_=0)
            ).label("skipped"),
        )
        .where(TestExecution.test_run_id.is_not(None))
        .group_by(TestExecution.test_run_id)
        .subquery()
    )
    rows = db.session.execute(
        db.select(
            TestRun,
            Project.name.label("project_name"),
            Version.name.label("version_name"),
            func.coalesce(stats.c.total, 0).label("total"),
            func.coalesce(stats.c.passed, 0).label("passed"),
            func.coalesce(stats.c.failed, 0).label("failed"),
            func.coalesce(stats.c.skipped, 0).label("skipped"),
        )
        .join(Version, TestRun.version_id == Version.id)
        .join(Project, Version.project_id == Project.id)
        .outerjoin(stats, stats.c.test_run_id == TestRun.id)
        .order_by(TestRun.imported_at.desc(), TestRun.id.desc())
    ).all()
    run_rows = [
        {
            "run": row.TestRun,
            "project_name": row.project_name,
            "version_name": row.version_name,
            "total": row.total,
            "passed": row.passed,
            "failed": row.failed,
            "skipped": row.skipped,
        }
        for row in rows
    ]
    return render_template("test_runs/index.html", run_rows=run_rows)


@bp.route("/import", methods=["GET", "POST"])
def import_report():
    form_data = {
        "version_id": request.form.get("version_id", "").strip(),
        "runner": request.form.get("runner", "").strip(),
        "environment": request.form.get("environment", "").strip(),
    }
    errors = []
    validation_items = []

    if request.method == "POST":
        version = _selected_version(form_data["version_id"])
        if not form_data["version_id"]:
            errors.append("请选择目标版本。")
        elif version is None:
            errors.append("目标版本不存在，请重新选择。")

        upload = request.files.get("junit_file")
        if upload is None or not upload.filename:
            errors.append("请选择 JUnit XML 文件。")
        elif not upload.filename.lower().endswith(".xml"):
            errors.append("仅支持 .xml 文件。")

        content = None
        if not errors:
            max_size = ParserConfig().max_file_size_bytes
            content = upload.stream.read(max_size + 1)
            if not content:
                errors.append("JUnit XML 文件不能为空。")

        if not errors:
            try:
                parsed_report = JUnitXmlParser().parse(content)
                result = JUnitImportService().import_report(
                    parsed_report=parsed_report,
                    version_id=version.id,
                    runner=form_data["runner"] or None,
                    environment=form_data["environment"] or None,
                    imported_at=current_app.config.get("JUNIT_IMPORT_NOW"),
                )
            except JUnitParseError as exc:
                errors.append(
                    PARSER_ERROR_MESSAGES.get(
                        exc.code,
                        "JUnit XML 解析失败，请检查报告内容。",
                    )
                )
            except JUnitImportValidationError as exc:
                if exc.code == "version_not_found":
                    errors.append("目标版本不存在，请重新选择。")
                else:
                    errors.append("JUnit 报告存在无法匹配的测试用例，未写入任何数据。")
                validation_items = [
                    {
                        "external_case_key": item.external_case_key,
                        "suite_path": " / ".join(item.suite_path),
                        "classname": item.classname or "-",
                        "testcase_name": item.testcase_name,
                        "test_case_code": item.test_case_code or "-",
                        "reason": VALIDATION_REASON_MESSAGES.get(
                            item.reason,
                            "测试结果无法安全导入",
                        ),
                    }
                    for item in exc.items
                ]
            except JUnitImportPersistenceError:
                errors.append("数据库导入失败，未写入任何执行记录。")
            else:
                if result.status == "already_imported":
                    flash("该报告已导入，已返回现有 TestRun。", "info")
                else:
                    flash("JUnit 报告导入成功。", "success")
                return redirect(
                    url_for(
                        "test_runs.detail",
                        test_run_id=result.test_run_id,
                        import_status=result.status,
                        imported_count=result.imported_count,
                    )
                )

    return _render_import_form(form_data, errors, validation_items)


@bp.get("/<int:test_run_id>")
def detail(test_run_id):
    test_run = db.session.scalar(
        db.select(TestRun)
        .where(TestRun.id == test_run_id)
        .options(
            joinedload(TestRun.version).joinedload(Version.project),
            selectinload(TestRun.executions),
        )
    )
    if test_run is None:
        abort(404)

    counts = Counter(execution.result for execution in test_run.executions)
    import_status = request.args.get("import_status")
    if import_status not in {"imported", "already_imported"}:
        import_status = None
    imported_count = request.args.get("imported_count", type=int)
    return render_template(
        "test_runs/detail.html",
        test_run=test_run,
        executions=sorted(
            test_run.executions,
            key=lambda execution: (execution.executed_at, execution.id),
        ),
        counts={
            "total": len(test_run.executions),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
        },
        import_status=import_status,
        imported_count=imported_count,
    )


def _selected_version(version_id):
    if not version_id.isdigit():
        return None
    return db.session.get(Version, int(version_id))


def _render_import_form(form_data, errors, validation_items):
    versions = db.session.scalars(
        db.select(Version)
        .options(joinedload(Version.project))
        .order_by(Project.name, Version.name)
        .join(Version.project)
    ).all()
    return render_template(
        "test_runs/import.html",
        errors=errors,
        validation_items=validation_items,
        versions=versions,
        selected_version_id=form_data["version_id"],
        runner=form_data["runner"],
        environment=form_data["environment"],
    )
