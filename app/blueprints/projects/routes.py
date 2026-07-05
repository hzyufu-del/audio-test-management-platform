from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Project


bp = Blueprint("projects", __name__, url_prefix="/projects")
PROJECT_STATUSES = ("active", "archived")


@bp.get("/")
def index():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("projects/index.html", projects=projects)


@bp.route("/new", methods=["GET", "POST"])
def create():
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_project_form_data()
        project = Project()
        errors = validate_project_form(form_data, project)

        if not errors and save_project(project, form_data, errors):
            flash("项目已创建。", "success")
            return redirect(url_for("projects.detail", project_id=project.id))

    return render_template(
        "projects/form.html",
        errors=errors,
        form_data=form_data,
        project=None,
        selected_status=get_selected_status(form_data, None),
        statuses=PROJECT_STATUSES,
        page_title="新增项目",
    )


@bp.get("/<int:project_id>")
def detail(project_id):
    project = db.get_or_404(Project, project_id)
    return render_template("projects/detail.html", project=project)


@bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
def edit(project_id):
    project = db.get_or_404(Project, project_id)
    form_data = None
    errors = []

    if request.method == "POST":
        form_data = get_project_form_data()
        errors = validate_project_form(form_data, project)

        if not errors and save_project(project, form_data, errors):
            flash("项目已更新。", "success")
            return redirect(url_for("projects.detail", project_id=project.id))

    return render_template(
        "projects/form.html",
        errors=errors,
        form_data=form_data,
        project=project,
        selected_status=get_selected_status(form_data, project),
        statuses=PROJECT_STATUSES,
        page_title="编辑项目",
    )


@bp.post("/<int:project_id>/delete")
def delete(project_id):
    project = db.get_or_404(Project, project_id)

    try:
        db.session.delete(project)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("该项目存在关联数据，当前基础 CRUD 阶段请先改为 archived 或清理关联数据。", "warning")
        return redirect(url_for("projects.detail", project_id=project.id))

    flash("项目已删除。", "success")
    return redirect(url_for("projects.index"))


def get_project_form_data():
    return {
        "name": request.form.get("name", "").strip(),
        "code": request.form.get("code", "").strip().upper(),
        "description": request.form.get("description", "").strip(),
        "status": request.form.get("status", "active").strip(),
    }


def validate_project_form(form_data, project):
    errors = []

    if not form_data["name"]:
        errors.append("项目名称不能为空。")

    if not form_data["code"]:
        errors.append("项目编码不能为空。")

    if form_data["status"] not in PROJECT_STATUSES:
        errors.append("项目状态只能是 active 或 archived。")

    if form_data["code"]:
        existing_project = Project.query.filter(
            Project.code == form_data["code"],
            Project.id != project.id,
        ).first()
        if existing_project:
            errors.append("项目编码已存在，请使用另一个 mock/demo/sample 编码。")

    return errors


def save_project(project, form_data, errors):
    project.name = form_data["name"]
    project.code = form_data["code"]
    project.description = form_data["description"]
    project.status = form_data["status"]
    db.session.add(project)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        errors.append("项目编码已存在，请使用另一个 mock/demo/sample 编码。")
        return False

    return True


def get_selected_status(form_data, project):
    if form_data:
        return form_data["status"]
    if project:
        return project.status
    return "active"
