from flask import jsonify, url_for

from app.services.testcase_service import (
    TESTCASE_PRIORITIES,
    TESTCASE_STATUSES,
    TestCaseService,
)

from . import bp
from .request_parsing import (
    parse_choice,
    parse_pagination,
    parse_positive_int,
    parse_text,
    require_json,
)
from .schemas import TestCaseCreateRequest
from .serializers import (
    serialize_pagination,
    serialize_test_case,
)


@bp.get("/test-cases")
def test_case_list():
    page, page_size = parse_pagination()
    pagination = TestCaseService.list_test_cases(
        page=page,
        page_size=page_size,
        project_id=parse_positive_int("project_id"),
        version_id=parse_positive_int("version_id"),
        module=parse_text("module"),
        priority=parse_choice("priority", TESTCASE_PRIORITIES),
        status=parse_choice("status", TESTCASE_STATUSES),
        keyword=parse_text("keyword"),
    )
    return jsonify(
        {
            "items": [
                serialize_test_case(test_case)
                for test_case in pagination.items
            ],
            "pagination": serialize_pagination(pagination),
        }
    )


@bp.get("/test-cases/<int:test_case_id>")
def test_case_detail(test_case_id):
    test_case = TestCaseService.get_test_case(test_case_id)
    return jsonify(serialize_test_case(test_case, detail=True))


@bp.post("/test-cases")
def test_case_create():
    request_model = require_json(TestCaseCreateRequest)
    test_case = TestCaseService.create_test_case(
        request_model.model_dump()
    )
    response = jsonify(serialize_test_case(test_case, detail=True))
    response.status_code = 201
    response.headers["Location"] = url_for(
        "api_v1.test_case_detail",
        test_case_id=test_case.id,
    )
    return response
