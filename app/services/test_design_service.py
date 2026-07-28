import json

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Project,
    TestCase,
    TestCaseDraft,
    TestDesignSession,
    Version,
)

from .ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIResponseError,
    AIReviewDisabledError,
    AIReviewError,
)
from .test_design.deepseek_provider import DeepSeekTestDesignProvider
from .test_design.mock_provider import MockTestDesignProvider
from .test_design.quality import score_test_design
from .test_design.schemas import (
    DraftEditInput,
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


PROMPT_VERSION = "test-design-v1"


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
        try:
            raw_result = provider.generate(context)
        except AIReviewError:
            raise
        except Exception:
            raise AIProviderError(
                "AI test design could not be generated. No draft was saved."
            ) from None

        try:
            result = TestDesignResult.model_validate(raw_result)
        except ValidationError:
            raise AIResponseError(
                "AI test design output failed strict schema validation."
            ) from None
        if (
            contains_forbidden_content(result)
            or not contains_demo_scope(result)
        ):
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

        session = TestDesignSession(
            project_id=project.id,
            version_id=version.id,
            title=context.title,
            requirement_text=context.requirement_text,
            status="generated",
            provider=provider.provider_name,
            provider_model=provider.provider_model,
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
        for draft_data in result.case_drafts:
            session.drafts.append(
                TestCaseDraft(
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
                )
            )
        db.session.add(session)

        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError(
                "Test design could not be saved. No data was written."
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

    def update_draft(self, draft_id, data):
        draft = self.get_draft(draft_id)
        self._require_pending(draft)
        validated = DraftEditInput.model_validate(data)
        self._require_safe_draft_content(validated)
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
        self._commit_draft_change(
            "TestCase Draft could not be updated."
        )
        return draft

    def accept_draft(self, draft_id):
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

    def reject_draft(self, draft_id):
        draft = self.get_draft(draft_id)
        self._require_pending(draft)
        draft.status = "rejected"
        draft.accepted_test_case_id = None
        self._update_session_status(draft.session)
        self._commit_draft_change(
            "Draft rejection could not be saved."
        )
        return draft

    @staticmethod
    def session_result(session):
        return TestDesignResult.model_validate(
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

    @staticmethod
    def _validate_context(title, requirement_text):
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
            (context.title, context.requirement_text)
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

    @staticmethod
    def _validated_draft(draft):
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
        TestDesignService._require_safe_draft_content(validated)
        return validated

    @staticmethod
    def _require_safe_draft_content(validated):
        if (
            contains_forbidden_content(validated)
            or not contains_demo_scope(validated)
        ):
            raise TestDesignValidationError(
                "Draft content must remain mock/demo/sample-only and cannot "
                "contain forbidden sensitive content."
            )

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
