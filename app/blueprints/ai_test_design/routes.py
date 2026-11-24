import json
import secrets

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from pydantic import ValidationError

from app.extensions import db
from app.models import GenerationRun, Project, TestCaseDraft, TestDesignSession, Version
from app.services.ai.exceptions import AIReviewError
from app.services.test_design.reviews import review_metrics
from app.services.test_design.diagnostics import sanitize_validation_summary
from app.services.test_design.submissions import valid_request_key
from app.services.test_design.schemas import (
    CaseType,
    Priority,
    ScenarioType,
)
from app.services.test_design_service import (
    TestDesignService,
    TestDesignValidationError,
)
from app.services.workflow_errors import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
)


bp = Blueprint(
    "ai_test_design",
    __name__,
    url_prefix="/ai-test-design",
)
SESSION_STATUSES = (
    "generated",
    "partially_reviewed",
    "accepted",
    "rejected",
)
PROVIDERS = ("mock", "deepseek")
DRAFT_FORM_FIELDS = {
    "suggested_code",
    "title",
    "module",
    "priority",
    "case_type",
    "scenario_type",
    "precondition",
    "steps",
    "expected_result",
}


@bp.get("/")
def index():
    service = TestDesignService(current_app.config)
    filters = {
        "project_id": _optional_int(request.args.get("project_id")),
        "version_id": _optional_int(request.args.get("version_id")),
        "status": request.args.get("status", "").strip(),
        "provider": request.args.get("provider", "").strip(),
    }
    sessions = service.list_sessions(**filters)
    rows = []
    for session in sessions:
        counts = {"pending": 0, "accepted": 0, "rejected": 0}
        for draft in session.drafts:
            counts[draft.status] += 1
        rows.append(
            {
                "session": session,
                "counts": counts,
                "total": len(session.drafts),
            }
        )
    return render_template(
        "ai_test_design/index.html",
        rows=rows,
        orphan_runs=_orphan_generation_runs(filters),
        projects=_projects(),
        versions=_versions(),
        filters={
            key: "" if value is None else value
            for key, value in filters.items()
        },
        statuses=SESSION_STATUSES,
        providers=PROVIDERS,
    )


@bp.route("/new", methods=["GET", "POST"])
def create():
    request_key = request.form.get("request_key", "") if request.method == "POST" else secrets.token_urlsafe(32)
    last_run_id = None
    form_data = {
        "project_id": request.form.get("project_id", "").strip(),
        "version_id": request.form.get("version_id", "").strip(),
        "title": request.form.get("title", "").strip(),
        "requirement_text": request.form.get(
            "requirement_text",
            "",
        ).strip(),
    }
    errors = []
    if request.method == "POST":
        if not valid_request_key(request_key):
            errors.append("Invalid submission key. Reload the form before generating.")
            request_key = secrets.token_urlsafe(32)
        project_id = _required_int(
            form_data["project_id"],
            "Project is required.",
            errors,
        )
        version_id = _required_int(
            form_data["version_id"],
            "Version is required.",
            errors,
        )
        if not errors:
            try:
                session = TestDesignService(
                    current_app.config
                ).create_session(
                    project_id=project_id,
                    version_id=version_id,
                    title=form_data["title"],
                    requirement_text=form_data["requirement_text"],
                    request_key=request_key,
                )
            except (
                AIReviewError,
                TestDesignValidationError,
                WorkflowConflictError,
                WorkflowNotFoundError,
                WorkflowPersistenceError,
            ) as exc:
                errors.append(str(exc))
                details = getattr(exc, "details", {})
                last_run_id = getattr(exc, "run_id", None) or details.get("run_id")
                if last_run_id is not None:
                    recorded = db.session.get(GenerationRun, last_run_id)
                    if recorded is not None and recorded.status == "failed":
                        # A new key is only usable after a deliberate new submit;
                        # rendering this form never dispatches another model call.
                        request_key = secrets.token_urlsafe(32)
                        errors.append("The attempt failed. Review its run record; submit again only to start a new attempt.")
            else:
                flash(
                    "AI Test Design drafts generated. Human review required.",
                    "success",
                )
                return redirect(
                    url_for(
                        "ai_test_design.detail",
                        session_id=session.id,
                    )
                )

    return render_template(
        "ai_test_design/new.html",
        errors=errors,
        form_data=form_data,
        projects=_projects(),
        versions=_versions(),
        request_key=request_key,
        last_run_id=last_run_id,
        failed_run_id=last_run_id,
        runtime_provider=("invalid" if current_app.config.get("AI_CONFIG_ERROR") else current_app.config.get("AI_PROVIDER", "mock")),
        runtime_ai_enabled=bool(current_app.config.get("AI_ENABLED", False)),
        runtime_config_error=("AI configuration is invalid. Correct local settings before generating."
                              if current_app.config.get("AI_CONFIG_ERROR") else ""),
    )


@bp.get("/runs/<int:run_id>")
def run_detail(run_id):
    run = db.get_or_404(GenerationRun, run_id)
    try:
        summary = sanitize_validation_summary(json.loads(run.validation_summary_json or "null"))
    except (TypeError, ValueError):
        summary = None
    return render_template("ai_test_design/run.html", run=run, validation_summary=summary)


@bp.get("/<int:session_id>")
def detail(session_id):
    session = db.get_or_404(TestDesignSession, session_id)
    service = TestDesignService(current_app.config)
    result = service.session_result(session)
    assessment = service.assessment_for_session(session)
    return render_template(
        "ai_test_design/detail.html",
        session=session,
        test_points=result.test_points,
        limitations=result.limitations,
        assessment=assessment,
        generation_runs=sorted(session.generation_runs, key=lambda run: run.id),
        review_history={
            draft.id: [
                {"record": record, "changed_fields": json.loads(record.changed_fields_json)}
                for record in sorted(draft.review_records, key=lambda record: record.id)
            ]
            for draft in session.drafts
        },
        metrics=review_metrics(session.drafts),
    )


@bp.route("/drafts/<int:draft_id>/edit", methods=["GET", "POST"])
@login_required
def edit_draft(draft_id):
    draft = db.get_or_404(TestCaseDraft, draft_id)
    errors = []
    status_code = 200
    expected_draft_revision = request.form.get("draft_revision") if request.method == "POST" else draft.revision
    expected_session_revision = request.form.get("session_revision") if request.method == "POST" else draft.session.review_revision
    form_data = _draft_form_data(draft)
    if request.method == "POST":
        form_data = {
            field: request.form.get(field, "").strip()
            for field in DRAFT_FORM_FIELDS
        }
        unknown_fields = set(request.form) - (DRAFT_FORM_FIELDS | {"comment", "draft_revision", "session_revision"})
        if unknown_fields:
            errors.append(
                "Unknown form field: "
                + ", ".join(sorted(unknown_fields))
                + "."
            )
        if not errors:
            try:
                TestDesignService(current_app.config).update_draft(
                    draft.id,
                    form_data,
                    reviewer_user_id=current_user.id,
                    comment=request.form.get("comment"),
                    **_review_versions(),
                )
            except ValidationError:
                errors.append(
                    "Draft fields failed strict validation."
                )
            except (
                TestDesignValidationError,
                WorkflowConflictError,
                WorkflowPersistenceError,
            ) as exc:
                errors.append(str(exc))
                if isinstance(exc, WorkflowConflictError):
                    status_code = 409
            else:
                flash("TestCase Draft updated.", "success")
                return redirect(
                    url_for(
                        "ai_test_design.detail",
                        session_id=draft.session_id,
                    )
                )
    return render_template(
        "ai_test_design/edit_draft.html",
        draft=draft,
        errors=errors,
        form_data=form_data,
        draft_revision=expected_draft_revision,
        session_revision=expected_session_revision,
        priorities=[item.value for item in Priority],
        case_types=[item.value for item in CaseType],
        scenario_types=[item.value for item in ScenarioType],
    ), status_code


@bp.post("/drafts/<int:draft_id>/accept")
@login_required
def accept_draft(draft_id):
    draft = db.get_or_404(TestCaseDraft, draft_id)
    session_id = draft.session_id
    try:
        test_case = TestDesignService(
            current_app.config
        ).accept_draft(
            draft.id,
            reviewer_user_id=current_user.id,
            comment=request.form.get("comment"),
            **_review_versions(),
        )
    except ValidationError:
        flash("Draft fields failed strict validation.", "danger")
        return redirect(
            url_for("ai_test_design.edit_draft", draft_id=draft.id)
        )
    except (
        TestDesignValidationError,
        WorkflowConflictError,
        WorkflowNotFoundError,
        WorkflowPersistenceError,
    ) as exc:
        flash(str(exc), "danger")
    else:
        flash(
            "Formal TestCase created after human review.",
            "success",
        )
        return redirect(
            url_for(
                "ai_test_design.detail",
                session_id=session_id,
                accepted_test_case_id=test_case.id,
            )
        )
    return redirect(
        url_for("ai_test_design.detail", session_id=session_id)
    )


@bp.post("/drafts/<int:draft_id>/reject")
@login_required
def reject_draft(draft_id):
    draft = db.get_or_404(TestCaseDraft, draft_id)
    session_id = draft.session_id
    try:
        TestDesignService(current_app.config).reject_draft(
            draft.id,
            reviewer_user_id=current_user.id,
            comment=request.form.get("comment"),
            **_review_versions(),
        )
    except (
        TestDesignValidationError,
        WorkflowConflictError,
        WorkflowNotFoundError,
        WorkflowPersistenceError,
    ) as exc:
        flash(str(exc), "danger")
    else:
        flash(
            "Draft rejected and did not enter the formal TestCase library.",
            "warning",
        )
    return redirect(
        url_for("ai_test_design.detail", session_id=session_id)
    )


def _review_versions():
    values = {}
    for name in ("draft_revision", "session_revision"):
        raw = request.form.get(name, "")
        if not raw.isascii() or not raw.isdigit() or len(raw) > 10 or int(raw) < 1:
            raise WorkflowConflictError("Review version is missing or invalid. Reload the draft before reviewing.")
        values[name] = int(raw)
    return values


def _projects():
    return Project.query.order_by(Project.name, Project.id).all()


def _versions():
    return Version.query.order_by(
        Version.project_id,
        Version.name,
        Version.id,
    ).all()


def _orphan_generation_runs(filters):
    query = GenerationRun.query.filter(
        GenerationRun.session_id.is_(None),
        GenerationRun.status.in_(("running", "failed")),
    )
    for field in ("project_id", "version_id", "provider"):
        if filters[field] is not None and filters[field] != "":
            query = query.filter(getattr(GenerationRun, field) == filters[field])
    return query.order_by(GenerationRun.created_at.desc(), GenerationRun.id.desc()).all()


def _optional_int(value):
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _required_int(value, message, errors):
    parsed = _optional_int(value)
    if parsed is None:
        errors.append(message)
    return parsed


def _draft_form_data(draft):
    return {
        "suggested_code": draft.suggested_code,
        "title": draft.title,
        "module": draft.module,
        "priority": draft.priority,
        "case_type": draft.case_type,
        "scenario_type": draft.scenario_type,
        "precondition": draft.precondition or "",
        "steps": draft.steps,
        "expected_result": draft.expected_result,
    }
