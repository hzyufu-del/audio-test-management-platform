from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Defect, Project, TestCase, TestExecution, Version

from .workflow_errors import (
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowPersistenceError,
)


DEFECT_SEVERITIES = ("blocker", "critical", "major", "minor")
DEFECT_PRIORITIES = ("P0", "P1", "P2", "P3")
DEFECT_STATUSES = ("open", "fixed", "closed", "rejected")
DEFECT_PATCH_FIELDS = (
    "status",
    "severity",
    "priority",
    "assignee",
    "resolution",
    "resolution_note",
)


class DefectService:
    @staticmethod
    def list_defects(
        *,
        page,
        page_size,
        project_id=None,
        version_id=None,
        test_execution_id=None,
        status=None,
        severity=None,
        priority=None,
        component=None,
        assignee=None,
        keyword=None,
    ):
        query = (
            Defect.query.options(
                joinedload(Defect.execution).joinedload(
                    TestExecution.testcase
                )
            )
            .join(Defect.execution)
            .join(TestExecution.testcase)
            .join(TestCase.version)
            .join(Version.project)
        )

        if project_id is not None:
            query = query.filter(Project.id == project_id)
        if version_id is not None:
            query = query.filter(Version.id == version_id)
        if test_execution_id is not None:
            query = query.filter(
                Defect.test_execution_id == test_execution_id
            )
        if status:
            query = query.filter(Defect.status == status)
        if severity:
            query = query.filter(Defect.severity == severity)
        if priority:
            query = query.filter(Defect.priority == priority)
        if component:
            query = query.filter(Defect.component == component)
        if assignee:
            query = query.filter(Defect.assignee == assignee)
        if keyword:
            query = query.filter(
                or_(
                    Defect.code.contains(keyword, autoescape=True),
                    Defect.title.contains(keyword, autoescape=True),
                    Defect.description.contains(keyword, autoescape=True),
                )
            )

        return query.order_by(
            Defect.created_at.desc(),
            Defect.id.desc(),
        ).paginate(page=page, per_page=page_size, error_out=False)

    @staticmethod
    def get_defect(defect_id):
        defect = (
            Defect.query.options(
                joinedload(Defect.execution).joinedload(
                    TestExecution.testcase
                )
            )
            .filter(Defect.id == defect_id)
            .first()
        )
        if defect is None:
            raise WorkflowNotFoundError("缺陷不存在。")
        return defect

    @staticmethod
    def create_defect(data):
        execution = db.session.get(
            TestExecution,
            data["test_execution_id"],
        )
        if execution is None:
            raise WorkflowNotFoundError("执行记录不存在。")
        if execution.result != "failed":
            raise WorkflowConflictError(
                "只能从 failed 执行记录创建缺陷。"
            )

        duplicate = Defect.query.filter_by(code=data["code"]).first()
        if duplicate is not None:
            raise WorkflowConflictError("缺陷编号已存在。")

        resolution = _nullable_text(data.get("resolution"))
        resolution_note = _nullable_text(data.get("resolution_note"))
        _validate_workflow_state(
            data["status"],
            resolution,
            resolution_note,
        )

        defect = Defect(
            code=data["code"],
            title=data["title"],
            description=data["description"],
            component=data["component"],
            severity=data["severity"],
            priority=data["priority"],
            status=data["status"],
            reproduction_steps=data["reproduction_steps"],
            observed_result=data["observed_result"],
            reporter=data["reporter"],
            assignee=_nullable_text(data.get("assignee")),
            resolution=resolution,
            resolution_note=resolution_note,
        )
        defect.capture_execution_snapshot(execution)
        db.session.add(defect)

        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError("缺陷编号已存在。") from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError("缺陷保存失败。") from exc

        return defect

    @classmethod
    def update_defect(cls, defect_id, data):
        defect = cls.get_defect(defect_id)
        normalized = {
            key: (
                _nullable_text(value)
                if key in {"assignee", "resolution", "resolution_note"}
                else value
            )
            for key, value in data.items()
        }
        status = normalized.get("status", defect.status)
        resolution = normalized.get("resolution", defect.resolution)
        resolution_note = normalized.get(
            "resolution_note",
            defect.resolution_note,
        )
        _validate_workflow_state(status, resolution, resolution_note)

        for field in DEFECT_PATCH_FIELDS:
            if field in normalized:
                setattr(defect, field, normalized[field])

        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise WorkflowConflictError(
                "缺陷更新与当前数据状态冲突。"
            ) from exc
        except SQLAlchemyError as exc:
            db.session.rollback()
            raise WorkflowPersistenceError("缺陷更新失败。") from exc

        return defect


def _nullable_text(value):
    return value if value not in ("", None) else None


def _validate_workflow_state(status, resolution, resolution_note):
    if status in {"fixed", "closed"} and not resolution:
        raise WorkflowConflictError(
            "fixed 或 closed 状态必须填写 resolution。"
        )
    if status == "open" and resolution:
        raise WorkflowConflictError(
            "open 状态不能携带 resolution。"
        )
    if status == "rejected" and not resolution_note:
        raise WorkflowConflictError(
            "rejected 状态必须填写 resolution_note。"
        )
