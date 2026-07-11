from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Defect, TestCase, TestExecution


bp = Blueprint("defects", __name__, url_prefix="/defects")
DEFECT_SEVERITIES = ("blocker", "critical", "major", "minor")
DEFECT_PRIORITIES = ("P0", "P1", "P2", "P3")
DEFECT_STATUSES = ("open", "fixed", "closed", "rejected")


@bp.get("/")
def index():
    defects = (
        Defect.query.join(Defect.execution)
        .join(TestExecution.testcase)
        .join(TestCase.version)
        .order_by(Defect.created_at.desc())
        .all()
    )
    return render_template("defects/index.html", defects=defects)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_defect_form_data()
        defect = Defect()
        errors = validate_defect_form(form_data, defect)

        if not errors and save_defect(defect, form_data, errors):
            flash("缺陷已创建。", "success")
            return redirect(url_for("defects.detail", defect_id=defect.id))

    return render_template_defect_form(
        page_title="新增缺陷",
        defect=None,
        form_data=form_data,
        errors=errors,
    )


@bp.get("/<int:defect_id>")
def detail(defect_id):
    defect = db.get_or_404(Defect, defect_id)
    return render_template("defects/detail.html", defect=defect)


@bp.route("/<int:defect_id>/edit", methods=["GET", "POST"])
def edit(defect_id):
    defect = db.get_or_404(Defect, defect_id)
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_defect_form_data()
        errors = validate_defect_form(form_data, defect)

        if not errors and save_defect(defect, form_data, errors):
            flash("缺陷已更新。", "success")
            return redirect(url_for("defects.detail", defect_id=defect.id))

    return render_template_defect_form(
        page_title="编辑缺陷",
        defect=defect,
        form_data=form_data,
        errors=errors,
    )


@bp.post("/<int:defect_id>/delete")
def delete(defect_id):
    defect = db.get_or_404(Defect, defect_id)

    db.session.delete(defect)
    db.session.commit()

    flash("缺陷已删除。", "success")
    return redirect(url_for("defects.index"))


def render_template_defect_form(page_title, defect, form_data, errors):
    executions = (
        TestExecution.query.join(TestExecution.testcase)
        .join(TestCase.version)
        .filter(TestExecution.result == "failed")
        .order_by(TestExecution.executed_at.desc())
        .all()
    )
    return render_template(
        "defects/form.html",
        defect=defect,
        errors=errors,
        executions=executions,
        form_data=form_data,
        page_title=page_title,
        priorities=DEFECT_PRIORITIES,
        selected_priority=get_selected_value(form_data, defect, "priority", "P2"),
        selected_severity=get_selected_value(form_data, defect, "severity", "major"),
        selected_status=get_selected_value(form_data, defect, "status", "open"),
        selected_test_execution_id=get_selected_execution_id(form_data, defect),
        severities=DEFECT_SEVERITIES,
        statuses=DEFECT_STATUSES,
    )


def get_defect_form_data():
    return {
        "test_execution_id": request.form.get("test_execution_id", "").strip(),
        "code": request.form.get("code", "").strip().upper(),
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "component": request.form.get("component", "").strip(),
        "severity": request.form.get("severity", "major").strip(),
        "priority": request.form.get("priority", "P2").strip(),
        "status": request.form.get("status", "open").strip(),
        "reproduction_steps": request.form.get("reproduction_steps", "").strip(),
        "observed_result": request.form.get("observed_result", "").strip(),
        "reporter": request.form.get("reporter", "").strip(),
        "assignee": request.form.get("assignee", "").strip(),
        "resolution": request.form.get("resolution", "").strip(),
        "resolution_note": request.form.get("resolution_note", "").strip(),
    }


def validate_defect_form(form_data, defect):
    errors = []

    if defect.id is None:
        execution = get_form_execution(form_data["test_execution_id"])
        if not form_data["test_execution_id"]:
            errors.append("来源执行记录不能为空。")
        elif execution is None:
            errors.append("来源执行记录不存在，请选择有效的 mock/demo/sample 执行记录。")
        elif execution.result != "failed":
            errors.append("只有 failed 执行记录可以创建缺陷。")

        if not form_data["code"]:
            errors.append("缺陷编号不能为空。")
        elif Defect.query.filter_by(code=form_data["code"]).first():
            errors.append("缺陷编号已存在，请使用其他 mock/demo/sample 编号。")

    required_fields = (
        ("title", "缺陷标题不能为空。"),
        ("description", "问题描述不能为空。"),
        ("component", "所属模块不能为空。"),
        ("reproduction_steps", "复现步骤不能为空。"),
        ("observed_result", "实际结果不能为空。"),
        ("reporter", "提交人不能为空，请使用 mock/demo/sample 用户名。"),
    )
    for field, message in required_fields:
        if not form_data[field]:
            errors.append(message)

    if form_data["severity"] not in DEFECT_SEVERITIES:
        errors.append("严重程度只能是 blocker、critical、major 或 minor。")
    if form_data["priority"] not in DEFECT_PRIORITIES:
        errors.append("优先级只能是 P0、P1、P2 或 P3。")
    if form_data["status"] not in DEFECT_STATUSES:
        errors.append("缺陷状态只能是 open、fixed、closed 或 rejected。")

    return errors


def save_defect(defect, form_data, errors):
    if defect.id is None:
        execution = get_form_execution(form_data["test_execution_id"])
        defect.code = form_data["code"]
        defect.capture_execution_snapshot(execution)

    defect.title = form_data["title"]
    defect.description = form_data["description"]
    defect.component = form_data["component"]
    defect.severity = form_data["severity"]
    defect.priority = form_data["priority"]
    defect.status = form_data["status"]
    defect.reproduction_steps = form_data["reproduction_steps"]
    defect.observed_result = form_data["observed_result"]
    defect.reporter = form_data["reporter"]
    defect.assignee = form_data["assignee"]
    defect.resolution = form_data["resolution"]
    defect.resolution_note = form_data["resolution_note"]
    db.session.add(defect)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        errors.append("缺陷保存失败，请确认编号唯一且来源执行记录仍然存在。")
        return False

    return True


def get_form_execution(execution_id):
    if not execution_id.isdigit():
        return None
    return db.session.get(TestExecution, int(execution_id))


def get_selected_execution_id(form_data, defect):
    if defect:
        return str(defect.test_execution_id)
    if form_data:
        return form_data["test_execution_id"]
    return ""


def get_selected_value(form_data, defect, field, default):
    if form_data:
        return form_data[field]
    if defect:
        return getattr(defect, field)
    return default
