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
    if request.method == "POST":
        project = Project()
        if save_project_from_form(project):
            flash("项目已创建。", "success")
            return redirect(url_for("projects.detail", project_id=project.id))

    return render_template(
        "projects/form.html",
        project=None,
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

    if request.method == "POST" and save_project_from_form(project):
        flash("项目已更新。", "success")
        return redirect(url_for("projects.detail", project_id=project.id))

    return render_template(
        "projects/form.html",
        project=project,
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


def save_project_from_form(project):
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    description = request.form.get("description", "").strip()
    status = request.form.get("status", "active").strip()

    if not name or not code:
        flash("项目名称和项目编码不能为空。", "warning")
        return False

    if status not in PROJECT_STATUSES:
        flash("项目状态只能是 active 或 archived。", "warning")
        return False

    existing_project = Project.query.filter(Project.code == code, Project.id != project.id).first()
    if existing_project:
        flash("项目编码已存在，请使用另一个 mock/demo/sample 编码。", "warning")
        return False

    project.name = name
    project.code = code
    project.description = description
    project.status = status
    db.session.add(project)
    db.session.commit()
    return True
