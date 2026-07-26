import json

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import LogFile, Project, Version
from ...services.log_analysis_service import (
    LogAnalysisConfig,
    LogAnalysisError,
    LogTextParser,
)


bp = Blueprint("logs", __name__, url_prefix="/logs")


@bp.get("/")
def index():
    log_files = (
        LogFile.query.options(
            joinedload(LogFile.project),
            joinedload(LogFile.version),
        )
        .order_by(LogFile.uploaded_at.desc(), LogFile.id.desc())
        .all()
    )
    return render_template("logs/index.html", log_files=log_files)


@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return _render_upload()

    project_id = request.form.get("project_id", type=int)
    if project_id is None:
        return _upload_error("Project is required.")

    project = db.session.get(Project, project_id)
    if project is None:
        return _upload_error("Selected Project does not exist.")

    version = None
    version_value = request.form.get("version_id", "").strip()
    if version_value:
        try:
            version_id = int(version_value)
        except ValueError:
            return _upload_error("Selected Version does not exist.")
        version = db.session.get(Version, version_id)
        if version is None:
            return _upload_error("Selected Version does not exist.")
        if version.project_id != project.id:
            return _upload_error(
                "Selected Version does not belong to the selected Project."
            )

    uploaded_file = request.files.get("log_file")
    if uploaded_file is None or not uploaded_file.filename:
        return _upload_error("Select a .log or .txt file.")

    parser_config = LogAnalysisConfig()
    content = uploaded_file.read(parser_config.max_file_size_bytes + 1)
    try:
        analysis = LogTextParser(parser_config).analyze(
            uploaded_file.filename,
            content,
        )
    except LogAnalysisError as exc:
        return _upload_error(exc.message)

    duplicate = LogFile.query.filter_by(
        project_id=project.id,
        sha256=analysis.sha256,
    ).first()
    if duplicate is not None:
        return _upload_error(
            "This log has already been analyzed for the selected Project."
        )

    uploaded_by = (
        current_user.username
        if current_user.is_authenticated
        else "anonymous_demo"
    )
    item = LogFile(
        project_id=project.id,
        version_id=version.id if version else None,
        filename=analysis.filename,
        file_size_bytes=analysis.file_size_bytes,
        sha256=analysis.sha256,
        analysis_status="completed",
        risk_level=analysis.risk_level,
        total_lines=analysis.total_lines,
        critical_count=analysis.level_counts["critical"],
        error_count=analysis.level_counts["error"],
        warning_count=analysis.level_counts["warning"],
        info_count=analysis.level_counts["info"],
        analysis_summary=analysis.summary_json,
        uploaded_by=uploaded_by,
        notes=request.form.get("notes", "").strip() or None,
    )
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        duplicate = LogFile.query.filter_by(
            project_id=project.id,
            sha256=analysis.sha256,
        ).first()
        if duplicate is not None:
            return _upload_error(
                "This log has already been analyzed for the selected Project."
            )
        return _upload_error(
            "Log analysis could not be saved. No data was written."
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _upload_error(
            "Log analysis could not be saved. No data was written."
        )

    flash("Log analysis completed.", "success")
    return redirect(url_for("logs.detail", log_id=item.id))


@bp.get("/<int:log_id>")
def detail(log_id):
    item = db.get_or_404(LogFile, log_id)
    try:
        summary = json.loads(item.analysis_summary)
    except (TypeError, json.JSONDecodeError):
        summary = {
            "domains": {},
            "findings": [],
            "findings_truncated": False,
        }
    return render_template(
        "logs/detail.html",
        log_file=item,
        summary=summary,
    )


def _render_upload():
    projects = Project.query.order_by(Project.name, Project.id).all()
    versions = (
        Version.query.options(joinedload(Version.project))
        .order_by(Version.project_id, Version.name, Version.id)
        .all()
    )
    return render_template(
        "logs/upload.html",
        projects=projects,
        versions=versions,
        selected_project_id=request.form.get("project_id", ""),
        selected_version_id=request.form.get("version_id", ""),
        notes=request.form.get("notes", ""),
    )


def _upload_error(message):
    flash(message, "danger")
    return _render_upload()
