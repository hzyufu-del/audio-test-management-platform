from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Project, Version


bp = Blueprint("versions", __name__, url_prefix="/versions")
VERSION_STATUSES = ("planned", "testing", "released", "archived")


@bp.get("/")
def index():
    versions = (
        Version.query.join(Project)
        .order_by(Version.created_at.desc())
        .all()
    )
    return render_template("versions/index.html", versions=versions)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_version_form_data()
        version = Version()
        errors = validate_version_form(form_data, version)

        if not errors and save_version(version, form_data, errors):
            flash("版本已创建。", "success")
            return redirect(url_for("versions.detail", version_id=version.id))

    return render_template_version_form(
        page_title="新增版本",
        version=None,
        form_data=form_data,
        errors=errors,
    )


@bp.get("/<int:version_id>")
def detail(version_id):
    version = db.get_or_404(Version, version_id)
    return render_template("versions/detail.html", version=version)


@bp.route("/<int:version_id>/edit", methods=["GET", "POST"])
def edit(version_id):
    version = db.get_or_404(Version, version_id)
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_version_form_data()
        errors = validate_version_form(form_data, version)

        if not errors and save_version(version, form_data, errors):
            flash("版本已更新。", "success")
            return redirect(url_for("versions.detail", version_id=version.id))

    return render_template_version_form(
        page_title="编辑版本",
        version=version,
        form_data=form_data,
        errors=errors,
    )


@bp.post("/<int:version_id>/delete")
def delete(version_id):
    version = db.get_or_404(Version, version_id)

    if version.testcases:
        flash("该版本下已有测试用例，不能直接删除。请先归档版本或清理关联用例。", "warning")
        return redirect(url_for("versions.detail", version_id=version.id))

    try:
        db.session.delete(version)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("该版本存在关联数据，当前基础 CRUD 阶段请先改为 archived 或清理关联数据。", "warning")
        return redirect(url_for("versions.detail", version_id=version.id))

    flash("版本已删除。", "success")
    return redirect(url_for("versions.index"))


def render_template_version_form(page_title, version, form_data, errors):
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template(
        "versions/form.html",
        errors=errors,
        form_data=form_data,
        projects=projects,
        selected_project_id=get_selected_project_id(form_data, version),
        selected_status=get_selected_status(form_data, version),
        statuses=VERSION_STATUSES,
        version=version,
        page_title=page_title,
    )


def get_version_form_data():
    return {
        "project_id": request.form.get("project_id", "").strip(),
        "name": request.form.get("name", "").strip(),
        "code": request.form.get("code", "").strip().upper(),
        "description": request.form.get("description", "").strip(),
        "status": request.form.get("status", "planned").strip(),
    }


def validate_version_form(form_data, version):
    errors = []
    project = get_form_project(form_data["project_id"])

    if not form_data["project_id"]:
        errors.append("所属项目不能为空。")
    elif project is None:
        errors.append("所属项目不存在，请选择一个有效的 mock/demo/sample 项目。")

    if not form_data["name"]:
        errors.append("版本名称不能为空。")

    if not form_data["code"]:
        errors.append("版本编码不能为空。")

    if form_data["status"] not in VERSION_STATUSES:
        errors.append("版本状态只能是 planned、testing、released 或 archived。")

    if project and form_data["code"]:
        query = Version.query.filter(
            Version.project_id == project.id,
            Version.code == form_data["code"],
        )
        if version.id is not None:
            query = query.filter(Version.id != version.id)

        if query.first():
            errors.append("同一项目下版本编码已存在，请使用另一个 mock/demo/sample 编码。")

    return errors


def save_version(version, form_data, errors):
    version.project_id = int(form_data["project_id"])
    version.name = form_data["name"]
    version.code = form_data["code"]
    version.description = form_data["description"]
    version.status = form_data["status"]
    version.release_type = "sample"
    db.session.add(version)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        errors.append("同一项目下版本编码已存在，请使用另一个 mock/demo/sample 编码。")
        return False

    return True


def get_form_project(project_id):
    if not project_id.isdigit():
        return None
    return db.session.get(Project, int(project_id))


def get_selected_project_id(form_data, version):
    if form_data:
        return form_data["project_id"]
    if version:
        return str(version.project_id)
    return ""


def get_selected_status(form_data, version):
    if form_data:
        return form_data["status"]
    if version:
        return version.status
    return "planned"
