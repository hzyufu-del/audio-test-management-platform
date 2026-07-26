from datetime import timezone
from decimal import Decimal


def serialize_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def serialize_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def serialize_pagination(pagination):
    return {
        "page": pagination.page,
        "page_size": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    }


def serialize_test_case(test_case, *, detail=False):
    version = test_case.version
    project = version.project if version is not None else None
    payload = {
        "id": test_case.id,
        "version_id": test_case.version_id,
        "version_code": version.code if version is not None else None,
        "project_id": version.project_id if version is not None else None,
        "project_code": project.code if project is not None else None,
        "code": test_case.code,
        "title": test_case.title,
        "module": test_case.module,
        "priority": test_case.priority,
        "case_type": test_case.case_type,
        "status": test_case.status,
        "created_at": serialize_datetime(test_case.created_at),
        "updated_at": serialize_datetime(test_case.updated_at),
    }
    if detail:
        payload.update(
            {
                "precondition": test_case.precondition,
                "steps": test_case.steps,
                "expected_result": test_case.expected_result,
            }
        )
    return payload


def serialize_execution(execution, *, detail=False):
    defects = sorted(execution.defects, key=lambda item: item.id)
    payload = {
        "id": execution.id,
        "test_case_id": execution.test_case_id,
        "test_case_code": execution.test_case_code_snapshot,
        "test_case_title": execution.test_case_title_snapshot,
        "result": execution.result,
        "tester": execution.tester,
        "environment": execution.environment,
        "executed_at": serialize_datetime(execution.executed_at),
        "has_defects": bool(defects),
        "defect_count": len(defects),
        "created_at": serialize_datetime(execution.created_at),
        "updated_at": serialize_datetime(execution.updated_at),
    }
    if detail:
        payload.update(
            {
                "actual_result": execution.actual_result,
                "notes": execution.notes,
                "duration_seconds": serialize_decimal(
                    execution.duration_seconds
                ),
                "external_case_key": execution.external_case_key,
                "test_run_id": execution.test_run_id,
                "test_case_code_snapshot": (
                    execution.test_case_code_snapshot
                ),
                "test_case_title_snapshot": (
                    execution.test_case_title_snapshot
                ),
                "precondition_snapshot": execution.precondition_snapshot,
                "steps_snapshot": execution.steps_snapshot,
                "expected_result_snapshot": (
                    execution.expected_result_snapshot
                ),
                "defects": [
                    {
                        "id": defect.id,
                        "code": defect.code,
                        "title": defect.title,
                        "status": defect.status,
                        "severity": defect.severity,
                    }
                    for defect in defects
                ],
            }
        )
    return payload


def serialize_defect(defect, *, detail=False):
    execution = defect.execution
    test_case = execution.testcase if execution is not None else None
    payload = {
        "id": defect.id,
        "code": defect.code,
        "title": defect.title,
        "test_execution_id": defect.test_execution_id,
        "test_case_code": (
            execution.test_case_code_snapshot
            if execution is not None
            else None
        ),
        "component": defect.component,
        "severity": defect.severity,
        "priority": defect.priority,
        "status": defect.status,
        "reporter": defect.reporter,
        "assignee": defect.assignee,
        "created_at": serialize_datetime(defect.created_at),
        "updated_at": serialize_datetime(defect.updated_at),
    }
    if detail:
        payload.update(
            {
                "description": defect.description,
                "reproduction_steps": defect.reproduction_steps,
                "observed_result": defect.observed_result,
                "resolution": defect.resolution,
                "resolution_note": defect.resolution_note,
                "environment_snapshot": defect.environment_snapshot,
                "actual_result_snapshot": defect.actual_result_snapshot,
                "executed_at_snapshot": serialize_datetime(
                    defect.executed_at_snapshot
                ),
                "execution": (
                    {
                        "id": execution.id,
                        "result": execution.result,
                        "test_case_id": execution.test_case_id,
                    }
                    if execution is not None
                    else None
                ),
                "test_case": (
                    {
                        "id": test_case.id if test_case is not None else None,
                        "code": execution.test_case_code_snapshot,
                        "title": execution.test_case_title_snapshot,
                    }
                    if execution is not None
                    else None
                ),
            }
        )
    return payload
