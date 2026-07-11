from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import TestCase, Version


bp = Blueprint("testcases", __name__, url_prefix="/test-cases")
TESTCASE_PRIORITIES = ("P0", "P1", "P2", "P3")
TESTCASE_STATUSES = ("draft", "active", "archived")


@bp.get("/")
def index():
    test_cases = (
        TestCase.query.join(Version)
        .order_by(TestCase.created_at.desc())
        .all()
    )
    return render_template("test_cases/index.html", test_cases=test_cases)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_test_case_form_data()
        test_case = TestCase()
        errors = validate_test_case_form(form_data, test_case)

        if not errors and save_test_case(test_case, form_data, errors):
            flash("用例已创建。", "success")
            return redirect(url_for("testcases.detail", test_case_id=test_case.id))

    return render_template_test_case_form(
        page_title="新增用例",
        test_case=None,
        form_data=form_data,
        errors=errors,
    )


@bp.get("/<int:test_case_id>")
def detail(test_case_id):
    test_case = db.get_or_404(TestCase, test_case_id)
    return render_template("test_cases/detail.html", test_case=test_case)


@bp.route("/<int:test_case_id>/edit", methods=["GET", "POST"])
def edit(test_case_id):
    test_case = db.get_or_404(TestCase, test_case_id)
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_test_case_form_data()
        errors = validate_test_case_form(form_data, test_case)

        if not errors and save_test_case(test_case, form_data, errors):
            flash("用例已更新。", "success")
            return redirect(url_for("testcases.detail", test_case_id=test_case.id))

    return render_template_test_case_form(
        page_title="编辑用例",
        test_case=test_case,
        form_data=form_data,
        errors=errors,
    )


@bp.post("/<int:test_case_id>/delete")
def delete(test_case_id):
    test_case = db.get_or_404(TestCase, test_case_id)

    if test_case.executions:
        flash("该用例下已有执行记录，不能直接删除。请先归档用例或清理关联执行记录。", "warning")
        return redirect(url_for("testcases.detail", test_case_id=test_case.id))

    try:
        db.session.delete(test_case)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("该用例存在关联执行记录，当前基础 CRUD 阶段请先归档或清理关联数据。", "warning")
        return redirect(url_for("testcases.detail", test_case_id=test_case.id))

    flash("用例已删除。", "success")
    return redirect(url_for("testcases.index"))


def render_template_test_case_form(page_title, test_case, form_data, errors):
    versions = Version.query.order_by(Version.created_at.desc()).all()
    return render_template(
        "test_cases/form.html",
        errors=errors,
        form_data=form_data,
        priorities=TESTCASE_PRIORITIES,
        selected_priority=get_selected_priority(form_data, test_case),
        selected_status=get_selected_status(form_data, test_case),
        selected_version_id=get_selected_version_id(form_data, test_case),
        statuses=TESTCASE_STATUSES,
        test_case=test_case,
        versions=versions,
        page_title=page_title,
    )


def get_test_case_form_data():
    return {
        "version_id": request.form.get("version_id", "").strip(),
        "title": request.form.get("title", "").strip(),
        "code": request.form.get("code", "").strip().upper(),
        "module": request.form.get("module", "").strip(),
        "priority": request.form.get("priority", "P2").strip(),
        "precondition": request.form.get("precondition", "").strip(),
        "steps": request.form.get("steps", "").strip(),
        "expected_result": request.form.get("expected_result", "").strip(),
        "status": request.form.get("status", "draft").strip(),
    }


def validate_test_case_form(form_data, test_case):
    errors = []
    version = get_form_version(form_data["version_id"])

    if not form_data["version_id"]:
        errors.append("所属版本不能为空。")
    elif version is None:
        errors.append("所属版本不存在，请选择一个有效的 mock/demo/sample 版本。")

    if not form_data["title"]:
        errors.append("用例标题不能为空。")

    if not form_data["code"]:
        errors.append("用例编号不能为空。")

    if not form_data["module"]:
        errors.append("用例所属模块不能为空。")

    if form_data["priority"] not in TESTCASE_PRIORITIES:
        errors.append("优先级只能是 P0、P1、P2 或 P3。")

    if not form_data["steps"]:
        errors.append("测试步骤不能为空。")

    if not form_data["expected_result"]:
        errors.append("预期结果不能为空。")

    if form_data["status"] not in TESTCASE_STATUSES:
        errors.append("用例状态只能是 draft、active 或 archived。")

    if version and form_data["code"]:
        query = TestCase.query.filter(
            TestCase.version_id == version.id,
            TestCase.code == form_data["code"],
        )
        if test_case.id is not None:
            query = query.filter(TestCase.id != test_case.id)

        if query.first():
            errors.append("同一版本下用例编号已存在，请使用另一个 mock/demo/sample 编号。")

    return errors


def save_test_case(test_case, form_data, errors):
    version = get_form_version(form_data["version_id"])
    test_case.version_id = version.id
    test_case.title = form_data["title"]
    test_case.code = form_data["code"]
    test_case.module = form_data["module"]
    test_case.priority = form_data["priority"]
    test_case.precondition = form_data["precondition"]
    test_case.steps = form_data["steps"]
    test_case.expected_result = form_data["expected_result"]
    test_case.status = form_data["status"]
    test_case.case_type = "checklist"
    db.session.add(test_case)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        errors.append("同一版本下用例编号已存在，请使用另一个 mock/demo/sample 编号。")
        return False

    return True


def get_form_version(version_id):
    if not version_id.isdigit():
        return None
    return db.session.get(Version, int(version_id))


def get_selected_version_id(form_data, test_case):
    if form_data:
        return form_data["version_id"]
    if test_case:
        return str(test_case.version_id)
    return ""


def get_selected_priority(form_data, test_case):
    if form_data:
        return form_data["priority"]
    if test_case:
        return test_case.priority
    return "P2"


def get_selected_status(form_data, test_case):
    if form_data:
        return form_data["status"]
    if test_case:
        return test_case.status
    return "draft"
