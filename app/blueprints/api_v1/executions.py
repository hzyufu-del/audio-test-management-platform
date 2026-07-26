from flask import jsonify, url_for

from app.services.execution_service import (
    EXECUTION_RESULTS,
    ExecutionService,
)

from . import bp
from .errors import APIError
from .request_parsing import (
    parse_aware_datetime,
    parse_choice,
    parse_pagination,
    parse_positive_int,
    parse_text,
    require_json,
)
from .schemas import ExecutionCreateRequest
from .serializers import serialize_execution, serialize_pagination


@bp.get("/executions")
def execution_list():
    page, page_size = parse_pagination()
    executed_from = parse_aware_datetime("executed_from")
    executed_to = parse_aware_datetime("executed_to")
    if (
        executed_from is not None
        and executed_to is not None
        and executed_from > executed_to
    ):
        raise APIError(
            "bad_request",
            "日期时间范围无效。",
            400,
            {
                "executed_from": [
                    "executed_from 不能晚于 executed_to。"
                ]
            },
        )

    pagination = ExecutionService.list_executions(
        page=page,
        page_size=page_size,
        project_id=parse_positive_int("project_id"),
        version_id=parse_positive_int("version_id"),
        test_case_id=parse_positive_int("test_case_id"),
        result=parse_choice("result", EXECUTION_RESULTS),
        tester=parse_text("tester"),
        environment=parse_text("environment"),
        executed_from=executed_from,
        executed_to=executed_to,
    )
    return jsonify(
        {
            "items": [
                serialize_execution(execution)
                for execution in pagination.items
            ],
            "pagination": serialize_pagination(pagination),
        }
    )


@bp.get("/executions/<int:execution_id>")
def execution_detail(execution_id):
    execution = ExecutionService.get_execution(execution_id)
    return jsonify(serialize_execution(execution, detail=True))


@bp.post("/executions")
def execution_create():
    request_model = require_json(ExecutionCreateRequest)
    execution = ExecutionService.create_execution(
        request_model.model_dump()
    )
    response = jsonify(serialize_execution(execution, detail=True))
    response.status_code = 201
    response.headers["Location"] = url_for(
        "api_v1.execution_detail",
        execution_id=execution.id,
    )
    return response
