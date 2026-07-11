from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import TestCase, TestExecution, Version, utc_now


bp = Blueprint("executions", __name__, url_prefix="/test-executions")
EXECUTION_RESULTS = ("passed", "failed", "blocked", "skipped")


@bp.get("/")
def index():
    executions = (
        TestExecution.query.join(TestExecution.testcase)
        .join(TestCase.version)
        .order_by(TestExecution.executed_at.desc(), TestExecution.created_at.desc())
        .all()
    )
    return render_template("test_executions/index.html", executions=executions)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_execution_form_data()
        execution = TestExecution()
        errors = validate_execution_form(form_data, execution)

        if not errors and save_execution(execution, form_data, errors):
            flash("执行记录已创建。", "success")
            return redirect(url_for("executions.detail", execution_id=execution.id))

    return render_template_execution_form(
        page_title="新增执行记录",
        execution=None,
        form_data=form_data,
        errors=errors,
    )


@bp.get("/<int:execution_id>")
def detail(execution_id):
    execution = db.get_or_404(TestExecution, execution_id)
    return render_template("test_executions/detail.html", execution=execution)


@bp.route("/<int:execution_id>/edit", methods=["GET", "POST"])
def edit(execution_id):
    execution = db.get_or_404(TestExecution, execution_id)
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_execution_form_data()
        errors = validate_execution_form(form_data, execution)

        if not errors and save_execution(execution, form_data, errors):
            flash("执行记录已更新。", "success")
            return redirect(url_for("executions.detail", execution_id=execution.id))

    return render_template_execution_form(
        page_title="编辑执行记录",
        execution=execution,
        form_data=form_data,
        errors=errors,
    )


@bp.post("/<int:execution_id>/delete")
def delete(execution_id):
    execution = db.get_or_404(TestExecution, execution_id)

    if execution.defects:
        flash("该执行记录下已有缺陷，不能直接删除。请先保留执行历史或清理关联缺陷。", "warning")
        return redirect(url_for("executions.detail", execution_id=execution.id))

    try:
        db.session.delete(execution)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("该执行记录存在关联数据，不能直接删除。", "warning")
        return redirect(url_for("executions.detail", execution_id=execution.id))

    flash("执行记录已删除。", "success")
    return redirect(url_for("executions.index"))


def render_template_execution_form(page_title, execution, form_data, errors):
    test_cases = (
        TestCase.query.join(Version)
        .order_by(Version.created_at.desc(), TestCase.code.asc())
        .all()
    )
    return render_template(
        "test_executions/form.html",
        errors=errors,
        execution=execution,
        form_data=form_data,
        page_title=page_title,
        results=EXECUTION_RESULTS,
        selected_result=get_selected_result(form_data, execution),
        selected_test_case_id=get_selected_test_case_id(form_data, execution),
        selected_executed_at=get_selected_executed_at(form_data, execution),
        test_cases=test_cases,
    )


def get_execution_form_data():
    return {
        "test_case_id": request.form.get("test_case_id", "").strip(),
        "result": request.form.get("result", "").strip(),
        "actual_result": request.form.get("actual_result", "").strip(),
        "tester": request.form.get("tester", "").strip(),
        "environment": request.form.get("environment", "").strip(),
        "executed_at": request.form.get("executed_at", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }


def validate_execution_form(form_data, execution):
    errors = []
    test_case = get_form_test_case(form_data["test_case_id"])

    if not form_data["test_case_id"]:
        errors.append("所属用例不能为空。")
    elif test_case is None:
        errors.append("所属用例不存在，请选择一个有效的 mock/demo/sample 用例。")
    elif execution.id is not None and test_case.id != execution.test_case_id:
        errors.append("执行记录创建后不能更换所属用例，以免历史快照失真。")

    if not form_data["result"]:
        errors.append("执行结果不能为空。")
    elif form_data["result"] not in EXECUTION_RESULTS:
        errors.append("执行结果只能是 passed、failed、blocked 或 skipped。")

    if form_data["result"] == "failed" and not form_data["actual_result"]:
        errors.append("失败结果必须填写实际结果。")

    if not form_data["tester"]:
        errors.append("执行人不能为空，请使用 mock/demo/sample 执行人名称。")

    if form_data["executed_at"] and parse_executed_at(form_data["executed_at"]) is None:
        errors.append("执行时间格式不正确，请使用页面提供的日期时间控件。")

    return errors


def save_execution(execution, form_data, errors):
    test_case = get_form_test_case(form_data["test_case_id"])
    if execution.id is None:
        execution.capture_test_case_snapshot(test_case)
    execution.result = form_data["result"]
    execution.actual_result = form_data["actual_result"]
    execution.tester = form_data["tester"]
    execution.environment = form_data["environment"]
    execution.executed_at = parse_executed_at(form_data["executed_at"]) or utc_now()
    execution.notes = form_data["notes"]
    db.session.add(execution)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        errors.append("执行记录保存失败，请确认关联用例仍然存在。")
        return False

    return True


def get_form_test_case(test_case_id):
    if not test_case_id.isdigit():
        return None
    return db.session.get(TestCase, int(test_case_id))


def parse_executed_at(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def get_selected_test_case_id(form_data, execution):
    if form_data:
        return form_data["test_case_id"]
    if execution:
        return str(execution.test_case_id)
    return ""


def get_selected_result(form_data, execution):
    if form_data:
        return form_data["result"]
    if execution:
        return execution.result
    return "passed"


def get_selected_executed_at(form_data, execution):
    if form_data:
        return form_data["executed_at"]
    if execution and execution.executed_at:
        return execution.executed_at.strftime("%Y-%m-%dT%H:%M")
    return ""
