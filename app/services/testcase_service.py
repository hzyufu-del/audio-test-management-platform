from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Project, TestCase, Version

from .workflow_errors import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
)


TESTCASE_PRIORITIES = ("P0", "P1", "P2", "P3")
TESTCASE_CASE_TYPES = ("checklist",)
TESTCASE_STATUSES = ("draft", "active", "archived")


class TestCaseService:
    @staticmethod
    def list_test_cases(
        *,
        page,
        page_size,
        project_id=None,
        version_id=None,
        module=None,
        priority=None,
        status=None,
        keyword=None,
    ):
        query = (
            TestCase.query.options(
                joinedload(TestCase.version).joinedload(Version.project)
            )
            .join(TestCase.version)
            .join(Version.project)
        )

        if project_id is not None:
            query = query.filter(Project.id == project_id)
        if version_id is not None:
            query = query.filter(TestCase.version_id == version_id)
        if module:
            query = query.filter(TestCase.module == module)
        if priority:
            query = query.filter(TestCase.priority == priority)
        if status:
            query = query.filter(TestCase.status == status)
        if keyword:
            query = query.filter(
                or_(
                    TestCase.code.contains(keyword, autoescape=True),
                    TestCase.title.contains(keyword, autoescape=True),
                )
            )

        return query.order_by(
            TestCase.created_at.desc(),
            TestCase.id.desc(),
        ).paginate(page=page, per_page=page_size, error_out=False)

    @staticmethod
    def get_test_case(test_case_id):
        test_case = db.session.get(TestCase, test_case_id)
        if test_case is None:
            raise WorkflowNotFoundError("测试用例不存在。")
        return test_case

    @staticmethod
    def create_test_case(data):
        version = db.session.get(Version, data["version_id"])
        if version is None:
            raise WorkflowNotFoundError("版本不存在。")

        duplicate = TestCase.query.filter_by(
            version_id=version.id,
            code=data["code"],
        ).first()
        if duplicate is not None:
            raise WorkflowConflictError("同一版本下测试用例编号已存在。")

        test_case = TestCase(
            version_id=version.id,
            code=data["code"],
            title=data["title"],
            module=data["module"],
            priority=data["priority"],
            case_type=data["case_type"],
            precondition=data.get("precondition"),
            steps=data["steps"],
            expected_result=data["expected_result"],
            status=data["status"],
        )
        db.session.add(test_case)

        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError(
                "同一版本下测试用例编号已存在。"
            ) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError(
                "测试用例保存失败。"
            ) from exc

        return test_case
