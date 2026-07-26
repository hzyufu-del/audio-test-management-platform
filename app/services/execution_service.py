from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import Project, TestCase, TestExecution, Version, utc_now

from .workflow_errors import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
)


EXECUTION_RESULTS = ("passed", "failed", "blocked", "skipped")


class ExecutionService:
    @staticmethod
    def list_executions(
        *,
        page,
        page_size,
        project_id=None,
        version_id=None,
        test_case_id=None,
        result=None,
        tester=None,
        environment=None,
        executed_from=None,
        executed_to=None,
    ):
        query = (
            TestExecution.query.options(
                joinedload(TestExecution.testcase),
                selectinload(TestExecution.defects),
            )
            .join(TestExecution.testcase)
            .join(TestCase.version)
            .join(Version.project)
        )

        if project_id is not None:
            query = query.filter(Project.id == project_id)
        if version_id is not None:
            query = query.filter(Version.id == version_id)
        if test_case_id is not None:
            query = query.filter(TestExecution.test_case_id == test_case_id)
        if result:
            query = query.filter(TestExecution.result == result)
        if tester:
            query = query.filter(TestExecution.tester == tester)
        if environment:
            query = query.filter(TestExecution.environment == environment)
        if executed_from is not None:
            query = query.filter(TestExecution.executed_at >= executed_from)
        if executed_to is not None:
            query = query.filter(TestExecution.executed_at <= executed_to)

        return query.order_by(
            TestExecution.executed_at.desc(),
            TestExecution.id.desc(),
        ).paginate(page=page, per_page=page_size, error_out=False)

    @staticmethod
    def get_execution(execution_id):
        execution = (
            TestExecution.query.options(
                joinedload(TestExecution.testcase),
                selectinload(TestExecution.defects),
            )
            .filter(TestExecution.id == execution_id)
            .first()
        )
        if execution is None:
            raise WorkflowNotFoundError("执行记录不存在。")
        return execution

    @staticmethod
    def create_execution(data):
        test_case = db.session.get(TestCase, data["test_case_id"])
        if test_case is None:
            raise WorkflowNotFoundError("测试用例不存在。")

        execution = TestExecution(
            result=data["result"],
            actual_result=_nullable_text(data.get("actual_result")),
            tester=data["tester"],
            environment=_nullable_text(data.get("environment")),
            executed_at=data.get("executed_at") or utc_now(),
            notes=_nullable_text(data.get("notes")),
            test_run_id=None,
            external_case_key=None,
            duration_seconds=None,
        )
        execution.capture_test_case_snapshot(test_case)
        db.session.add(execution)

        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError(
                "执行记录关联的测试用例已发生变化。"
            ) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError(
                "执行记录保存失败。"
            ) from exc

        return execution


def _nullable_text(value):
    return value if value not in ("", None) else None
