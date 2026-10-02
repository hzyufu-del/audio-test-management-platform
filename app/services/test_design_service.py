import json
from time import perf_counter

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Project,
    GenerationRun,
    TestCase,
    TestCaseDraft,
    TestDesignSession,
    Version,
    utc_now,
)

from .ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
    AIReviewDisabledError,
    AIReviewError,
)
from .test_design.deepseek_provider import DeepSeekTestDesignProvider
from .test_design.diagnostics import (
    set_validation_summary, summarize_validation_error, validation_summary,
)
from .test_design.evidence import GenerationRecorder, safe_error, safe_metadata
from .test_design.mock_provider import MockTestDesignProvider
from .test_design.prompts import PROMPT_VERSION
from .test_design.quality import score_test_design
from .test_design.reviews import (
    ReviewAuthenticationError,
    ReviewCommentValidationError,
    build_review_record,
    draft_snapshot,
    resolve_reviewer,
    validate_comment,
)
from .test_design.schemas import (
    DraftEditInput,
    PersistedTestDesignResult,
    TestDesignContext,
    TestDesignResult,
)
from .test_design.security import (
    contains_demo_scope,
    contains_forbidden_content,
    detect_untrusted_input_risks,
)
from .workflow_errors import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
)


class TestDesignValidationError(ValueError):
    """Raised for bounded user input that is safe to show in the UI."""


def calculate_session_status(statuses):
    values = list(statuses)
    if not values or all(value == "pending" for value in values):
        return "generated"
    if "pending" in values:
        return "partially_reviewed"
    if "accepted" in values:
        return "accepted"
    return "rejected"


class TestDesignService:
    def __init__(self, config, provider=None):
        self.config = config
        self.provider = provider

    def create_session(
        self,
        *,
        project_id,
        version_id,
        title,
        requirement_text,
    ):
        context = self._validate_context(title, requirement_text)
        project = db.session.get(Project, project_id)
        if project is None:
            raise WorkflowNotFoundError("Project does not exist.")
        version = db.session.get(Version, version_id)
        if version is None:
            raise WorkflowNotFoundError("Version does not exist.")
        if version.project_id != project.id:
            raise WorkflowConflictError(
                "Selected Version does not belong to the selected Project."
            )

        provider = self.provider or self._create_provider()
        return self._generate(context, project.id, version.id, provider)

    def generate_for_session(self, session_id):
        session = self.get_session(session_id)
        context = self._validate_context(session.title, session.requirement_text)
        provider = self.provider or self._create_provider()
        return self._generate(
            context, session.project_id, session.version_id, provider, session=session,
        )

    def _generate(self, context, project_id, version_id, provider, session=None):
        provider.last_call_metadata = None
        set_validation_summary(provider, None)
        recorder = GenerationRecorder(self.config)
        run_id = recorder.start(
            context=context, project_id=project_id, version_id=version_id,
            provider=provider, session_id=session.id if session else None,
        )
        started = perf_counter()
        structured_output = None
        try:
            try:
                raw_result = provider.generate(context)
            except ValidationError:
                # Third-party providers may validate their raw result themselves.
                raise
            except AIReviewError as exc:
                # Providers outside our adapter may use arbitrary exception
                # messages. Preserve the safe category, never their string.
                _, message = safe_error(exc)
                raise type(exc)(message) from None
            except Exception:
                set_validation_summary(provider, validation_summary("api", "api_unavailable"))
                raise AIProviderError(
                    "AI test design could not be generated. No draft was saved."
                ) from None
            result = TestDesignResult.model_validate(raw_result)
            if contains_forbidden_content(result, config=self.config):
                set_validation_summary(provider, validation_summary("output_safety", "sensitive_content"))
                raise AIResponseError(
                    "AI test design output failed safety validation."
                )
            if not contains_demo_scope(result):
                set_validation_summary(provider, validation_summary("output_safety", "missing_demo_scope"))
                raise AIResponseError(
                    "AI test design output failed safety validation."
                )

            risks = detect_untrusted_input_risks(context.requirement_text)
            if risks:
                payload = result.model_dump(mode="json")
                payload["limitations"] = _unique_strings(
                    [*risks, *result.limitations]
                )[:8]
                result = TestDesignResult.model_validate(payload)
            assessment = score_test_design(result, risk_warnings=risks)
            structured_output = _dump_json(result.model_dump(mode="json"))
        except ValidationError as exc:
            set_validation_summary(provider, summarize_validation_error(exc))
            recorder.fail(
                run_id, error=AIResponseError("Invalid schema."),
                metadata=safe_metadata(provider, self.config),
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )
            raise AIResponseError(
                "AI test design output failed strict schema validation."
            ) from None
        except Exception as exc:
            recorder.fail(
                run_id, error=exc, metadata=safe_metadata(provider, self.config),
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )
            raise

        metadata = safe_metadata(provider, self.config)
        session_values = dict(
            project_id=project_id,
            version_id=version_id,
            title=context.title,
            requirement_text=context.requirement_text,
            status="generated",
            provider=provider.provider_name,
            provider_model=metadata["provider_model"],
            prompt_version=PROMPT_VERSION,
            quality_score=assessment.quality_score,
            test_points_json=_dump_json(
                [
                    item.model_dump(mode="json")
                    for item in result.test_points
                ]
            ),
            limitations_json=_dump_json(result.limitations),
        )
        try:
            if session is None:
                session = TestDesignSession(**session_values)
                db.session.add(session)
            else:
                for name, value in session_values.items():
                    setattr(session, name, value)
            for draft_data in result.case_drafts:
                session.drafts.append(TestCaseDraft(
                    generation_run_id=run_id,
                    suggested_code=draft_data.suggested_code,
                    title=draft_data.title,
                    module=draft_data.module,
                    priority=draft_data.priority.value,
                    case_type=draft_data.case_type.value,
                    precondition=draft_data.precondition or None,
                    steps=draft_data.steps,
                    expected_result=draft_data.expected_result,
                    scenario_type=draft_data.scenario_type.value,
                    status="pending",
                ))
            self._update_session_status(session)
            session.quality_score = self.assessment_for_session(session).quality_score
            run = db.session.get(GenerationRun, run_id)
            run.session = session
            run.status = "succeeded"
            run.finished_at = utc_now()
            run.latency_ms = max(0, round((perf_counter() - started) * 1000))
            for name, value in metadata.items():
                if value is not None:
                    setattr(run, name, value)
            run.structured_output_json = structured_output
            db.session.commit()
        except SQLAlchemyError as exc:
            set_validation_summary(provider, validation_summary("business_persistence", "persistence_failure"))
            db.session.rollback()
            recorder.fail(
                run_id, error=WorkflowPersistenceError("Cannot save generation."),
                metadata=metadata,
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
                structured_output_json=structured_output,
            )
            raise WorkflowPersistenceError(
                "Test design could not be saved. Call evidence was retained."
            ) from exc
        return session

    def list_sessions(
        self,
        *,
        project_id=None,
        version_id=None,
        status=None,
        provider=None,
    ):
        query = TestDesignSession.query.options(
            joinedload(TestDesignSession.project),
            joinedload(TestDesignSession.version),
            joinedload(TestDesignSession.drafts),
        )
        if project_id is not None:
            query = query.filter(
                TestDesignSession.project_id == project_id
            )
        if version_id is not None:
            query = query.filter(
                TestDesignSession.version_id == version_id
            )
        if status:
            query = query.filter(TestDesignSession.status == status)
        if provider:
            query = query.filter(TestDesignSession.provider == provider)
        return query.order_by(
            TestDesignSession.created_at.desc(),
            TestDesignSession.id.desc(),
        ).all()

    @staticmethod
    def get_session(session_id):
        session = db.session.get(TestDesignSession, session_id)
        if session is None:
            raise WorkflowNotFoundError(
                "AI Test Design Session does not exist."
            )
        return session

    @staticmethod
    def get_draft(draft_id):
        draft = db.session.get(TestCaseDraft, draft_id)
        if draft is None:
            raise WorkflowNotFoundError("TestCase Draft does not exist.")
        return draft

    def update_draft(self, draft_id, data, *, reviewer_user_id=None, comment=None):
        reviewer, comment = self._review_identity(reviewer_user_id, comment)
        draft = self.get_draft(draft_id)
        self._require_pending(draft)
        validated = DraftEditInput.model_validate(data)
        self._require_safe_draft_content(validated)
        before = draft_snapshot(draft)
        score_before = self.assessment_for_session(draft.session).quality_score
        draft.suggested_code = validated.suggested_code
        draft.title = validated.title
        draft.module = validated.module
        draft.priority = validated.priority.value
        draft.case_type = validated.case_type.value
        draft.scenario_type = validated.scenario_type.value
        draft.precondition = validated.precondition or None
        draft.steps = validated.steps
        draft.expected_result = validated.expected_result
        draft.session.quality_score = self.assessment_for_session(
            draft.session
        ).quality_score
        db.session.add(build_review_record(
            draft, reviewer, "edit", before, score_before,
            draft.session.quality_score, comment,
            config=self.config,
        ))
        self._commit_draft_change(
            "TestCase Draft could not be updated."
        )
        return draft

    def accept_draft(self, draft_id, *, reviewer_user_id=None, comment=None):
        reviewer, comment = self._review_identity(reviewer_user_id, comment)
        draft = self.get_draft(draft_id)
        self._require_pending(draft)
        validated = self._validated_draft(draft)
        version = db.session.get(Version, draft.session.version_id)
        if version is None:
            raise WorkflowNotFoundError(
                "The Session Version no longer exists."
            )
        duplicate = TestCase.query.filter_by(
            version_id=version.id,
            code=validated.suggested_code,
        ).first()
        if duplicate is not None:
            raise WorkflowConflictError(
                "A TestCase with this code already exists in the Version."
            )
        before = draft_snapshot(draft)
        score_before = self.assessment_for_session(draft.session).quality_score

        test_case = TestCase(
            version_id=version.id,
            code=validated.suggested_code,
            title=validated.title,
            module=validated.module,
            priority=validated.priority.value,
            case_type=validated.case_type.value,
            precondition=validated.precondition or None,
            steps=validated.steps,
            expected_result=validated.expected_result,
            status="draft",
        )
        db.session.add(test_case)
        draft.status = "accepted"
        draft.accepted_test_case = test_case
        self._update_session_status(draft.session)

        try:
            db.session.flush()
            db.session.add(build_review_record(
                draft, reviewer, "accept", before, score_before,
                self.assessment_for_session(draft.session).quality_score, comment,
                config=self.config,
            ))
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError(
                "A TestCase with this code already exists in the Version."
            ) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError(
                "Draft acceptance failed. No TestCase was created."
            ) from exc
        return test_case

    def reject_draft(self, draft_id, *, reviewer_user_id=None, comment=None):
        reviewer, comment = self._review_identity(reviewer_user_id, comment)
        draft = self.get_draft(draft_id)
        self._require_pending(draft)
        before = draft_snapshot(draft)
        score_before = self.assessment_for_session(draft.session).quality_score
        draft.status = "rejected"
        draft.accepted_test_case_id = None
        self._update_session_status(draft.session)
        db.session.add(build_review_record(
            draft, reviewer, "reject", before, score_before,
            self.assessment_for_session(draft.session).quality_score, comment,
            config=self.config,
        ))
        self._commit_draft_change(
            "Draft rejection could not be saved."
        )
        return draft

    @staticmethod
    def session_result(session):
        return PersistedTestDesignResult.model_validate(
            {
                "summary": (
                    f"Demo AI Design persisted by the {session.provider} "
                    "provider for human review."
                ),
                "test_points": json.loads(session.test_points_json),
                "case_drafts": [
                    {
                        "suggested_code": draft.suggested_code,
                        "title": draft.title,
                        "module": draft.module,
                        "priority": draft.priority,
                        "case_type": draft.case_type,
                        "precondition": draft.precondition or "",
                        "steps": draft.steps,
                        "expected_result": draft.expected_result,
                        "scenario_type": draft.scenario_type,
                    }
                    for draft in session.drafts
                ],
                "limitations": json.loads(session.limitations_json),
            }
        )

    def assessment_for_session(self, session):
        limitations = json.loads(session.limitations_json)
        risks = [
            item
            for item in limitations
            if "prompt-injection" in item.casefold()
        ]
        return score_test_design(
            self.session_result(session),
            risk_warnings=risks,
        )

    def _create_provider(self):
        provider_name = self.config.get("AI_PROVIDER", "mock")
        if provider_name == "mock":
            return MockTestDesignProvider()
        if provider_name == "deepseek":
            if not self.config.get("AI_ENABLED", False):
                raise AIReviewDisabledError(
                    "DeepSeek test design is disabled. Mock remains available."
                )
            return DeepSeekTestDesignProvider(
                api_key=self.config.get("DEEPSEEK_API_KEY", ""),
                model=self.config.get("DEEPSEEK_MODEL", ""),
                base_url=self.config.get(
                    "DEEPSEEK_BASE_URL",
                    "https://api.deepseek.com",
                ),
                timeout_seconds=self.config.get(
                    "AI_REQUEST_TIMEOUT_SECONDS",
                    20,
                ),
                max_output_tokens=self.config.get(
                    "AI_MAX_OUTPUT_TOKENS",
                    2000,
                ),
            )
        raise AIConfigurationError(
            "AI_PROVIDER must be either mock or deepseek."
        )

    def _validate_context(self, title, requirement_text):
        try:
            context = TestDesignContext(
                title=title,
                requirement_text=requirement_text,
            )
        except ValidationError as exc:
            raise TestDesignValidationError(
                "Title and Requirement Text must satisfy the bounded form."
            ) from exc
        if contains_forbidden_content(
            (context.title, context.requirement_text), config=self.config,
        ):
            raise TestDesignValidationError(
                "Input contains forbidden sensitive or non-demo content."
            )
        if not contains_demo_scope(context.requirement_text):
            raise TestDesignValidationError(
                "Requirement Text must be explicitly scoped as mock, demo, "
                "or sample data."
            )
        return context

    @staticmethod
    def _require_pending(draft):
        if draft.status != "pending":
            raise WorkflowConflictError(
                "Only a pending TestCase Draft can be changed."
            )

    def _validated_draft(self, draft):
        validated = DraftEditInput(
            suggested_code=draft.suggested_code,
            title=draft.title,
            module=draft.module,
            priority=draft.priority,
            case_type=draft.case_type,
            scenario_type=draft.scenario_type,
            precondition=draft.precondition or "",
            steps=draft.steps,
            expected_result=draft.expected_result,
        )
        self._require_safe_draft_content(validated)
        return validated

    def _require_safe_draft_content(self, validated):
        if (
            contains_forbidden_content(validated, config=self.config)
            or not contains_demo_scope(validated)
        ):
            raise TestDesignValidationError(
                "Draft content must remain mock/demo/sample-only and cannot "
                "contain forbidden sensitive content."
            )

    def _review_identity(self, reviewer_user_id, comment):
        try:
            return resolve_reviewer(reviewer_user_id), validate_comment(comment, self.config)
        except (ReviewAuthenticationError, ReviewCommentValidationError) as exc:
            raise TestDesignValidationError(str(exc)) from None

    @staticmethod
    def _update_session_status(session):
        session.status = calculate_session_status(
            draft.status for draft in session.drafts
        )

    @staticmethod
    def _commit_draft_change(error_message):
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError(error_message) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError(error_message) from exc


def _dump_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _unique_strings(values):
    seen = set()
    unique = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
