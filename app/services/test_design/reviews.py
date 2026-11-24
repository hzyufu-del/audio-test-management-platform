import json

from flask import has_request_context
from flask_login import current_user

from app.extensions import db
from app.models import ReviewRecord, TestCaseDraft, User

from .schemas import DraftEditInput
from .security import contains_forbidden_content


CONTENT_FIELDS = tuple(DraftEditInput.model_fields)


class ReviewAuthenticationError(ValueError):
    """Raised when a review cannot be attributed to a persisted user."""


class ReviewCommentValidationError(ValueError):
    """Raised for bounded, safely reportable review-comment errors."""


def resolve_reviewer(reviewer_user_id=None) -> User:
    """Resolve an authenticated request user or a trusted internal user ID."""
    if reviewer_user_id is None:
        if not has_request_context() or not current_user.is_authenticated:
            raise ReviewAuthenticationError(
                "A signed-in reviewer is required to review a TestCase Draft."
            )
        request_user = current_user._get_current_object()
        if not isinstance(request_user, User):
            raise ReviewAuthenticationError(
                "The reviewer must be an existing registered user."
            )
        reviewer_user_id = request_user.id

    if type(reviewer_user_id) is not int or reviewer_user_id <= 0:
        raise ReviewAuthenticationError(
            "The reviewer must be an existing registered user."
        )
    reviewer = db.session.get(User, reviewer_user_id)
    if reviewer is None:
        raise ReviewAuthenticationError(
            "The reviewer must be an existing registered user."
        )
    return reviewer


def validate_comment(comment, config) -> str | None:
    if comment is None:
        return None
    if not isinstance(comment, str):
        raise ReviewCommentValidationError("Review comment must be text.")
    cleaned = comment.strip()
    if len(cleaned) > 1000:
        raise ReviewCommentValidationError(
            "Review comment cannot exceed 1000 characters."
        )
    if not cleaned:
        return None
    if contains_forbidden_content(cleaned, config=config):
        raise ReviewCommentValidationError(
            "Review comment contains forbidden sensitive content."
        )
    return cleaned


def draft_snapshot(draft: TestCaseDraft) -> dict:
    snapshot = {field: getattr(draft, field) for field in CONTENT_FIELDS}
    snapshot["precondition"] = draft.precondition or ""
    snapshot["status"] = draft.status
    snapshot["accepted_test_case_id"] = draft.accepted_test_case_id
    return snapshot


def build_review_record(
    draft,
    reviewer,
    action,
    before,
    score_before,
    score_after,
    comment=None,
    *,
    config=None,
) -> ReviewRecord:
    """Build an unsaved record using caller-supplied Session quality scores."""
    after = draft_snapshot(draft)
    changed_fields = sorted(
        field for field in CONTENT_FIELDS
        if _comparison_value(field, before[field]) != _comparison_value(field, after[field])
    )
    return ReviewRecord(
        draft=draft,
        reviewer_user_id=reviewer.id,
        action=action,
        before_snapshot_json=_dump_json(_safe_snapshot(before, config)),
        after_snapshot_json=_dump_json(_safe_snapshot(after, config)),
        score_before=score_before,
        score_after=score_after,
        changed_fields_json=_dump_json(changed_fields),
        changed_field_count=len(changed_fields),
        comment=comment,
    )


def _comparison_value(field, value):
    # Browser form submission can change LF to CRLF without a steps edit.
    # Normalize only this comparison value; retain original stored snapshots.
    if field == "steps" and isinstance(value, str):
        return value.replace("\r\n", "\n")
    return value


def _safe_snapshot(snapshot, config):
    """Legacy content can be rejected without copying secrets into evidence."""
    values = dict(snapshot)
    redacted = []
    for field, value in snapshot.items():
        if isinstance(value, str) and contains_forbidden_content(value, config=config):
            values[field] = "[redacted sensitive content]"
            redacted.append(field)
    if redacted:
        values["redacted_fields"] = sorted(redacted)
    return values


def review_metrics(drafts) -> dict:
    values = list(drafts)
    total = len(values)
    changed_edits = []
    edited_drafts = 0
    review_count = 0
    for draft in values:
        edits = [
            record
            for record in draft.review_records
            if record.action == "edit" and record.changed_field_count > 0
        ]
        edited_drafts += bool(edits)
        changed_edits.extend(edits)
        review_count += len(draft.review_records)

    accepted = sum(draft.status == "accepted" for draft in values)
    rejected = sum(draft.status == "rejected" for draft in values)
    return {
        "total_drafts": total,
        "edited_drafts": edited_drafts,
        "edit_rate": edited_drafts / total if total else 0.0,
        "average_changed_fields": (
            sum(record.changed_field_count for record in changed_edits)
            / len(changed_edits)
            if changed_edits
            else 0.0
        ),
        "accepted_count": accepted,
        "rejected_count": rejected,
        "acceptance_rate": accepted / total if total else 0.0,
        "rejection_rate": rejected / total if total else 0.0,
        "review_count": review_count,
    }


def _dump_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
