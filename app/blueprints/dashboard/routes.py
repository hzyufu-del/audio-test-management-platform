from flask import Blueprint, current_app, flash, render_template, request

from ...extensions import db
from ...models import Project, Version
from ...services.dashboard_service import build_dashboard


bp = Blueprint("dashboard", __name__)
VALID_RANGES = {"7d", "30d", "all"}


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@bp.get("/")
def index():
    requested_project = request.args.get("project_id", "").strip()
    requested_version = request.args.get("version_id", "").strip()
    range_key = request.args.get("range", "30d").strip()

    project_id = _positive_int(requested_project)
    version_id = _positive_int(requested_version)

    project = db.session.get(Project, project_id) if project_id else None
    if requested_project and project is None:
        project_id = None
        flash("项目筛选无效，已回退为全部项目。", "warning")

    version = db.session.get(Version, version_id) if version_id else None
    if requested_version and version is None:
        version_id = None
        flash("版本筛选无效，已回退为全部版本。", "warning")
    elif version is not None and project_id is not None:
        if version.project_id != project_id:
            version_id = None
            flash("所选版本不属于当前项目，已回退为全部版本。", "warning")

    if range_key not in VALID_RANGES:
        range_key = "30d"
        flash("时间范围无效，已回退为最近 30 天。", "warning")

    projects = db.session.scalars(
        db.select(Project).order_by(Project.name, Project.id)
    ).all()
    version_query = db.select(Version).order_by(Version.name, Version.id)
    if project_id is not None:
        version_query = version_query.where(Version.project_id == project_id)
    versions = db.session.scalars(version_query).all()

    dashboard = build_dashboard(
        project_id=project_id,
        version_id=version_id,
        range_key=range_key,
        now=current_app.config.get("DASHBOARD_NOW"),
    )
    return render_template(
        "dashboard/index.html",
        dashboard=dashboard,
        projects=projects,
        versions=versions,
        selected_project_id=project_id,
        selected_version_id=version_id,
    )
