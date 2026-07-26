from flask import jsonify, url_for

from app.services.defect_service import (
    DEFECT_PRIORITIES,
    DEFECT_SEVERITIES,
    DEFECT_STATUSES,
    DefectService,
)

from . import bp
from .request_parsing import (
    parse_choice,
    parse_pagination,
    parse_positive_int,
    parse_text,
    require_json,
)
from .schemas import DefectCreateRequest, DefectPatchRequest
from .serializers import serialize_defect, serialize_pagination


@bp.get("/defects")
def defect_list():
    page, page_size = parse_pagination()
    pagination = DefectService.list_defects(
        page=page,
        page_size=page_size,
        project_id=parse_positive_int("project_id"),
        version_id=parse_positive_int("version_id"),
        test_execution_id=parse_positive_int("test_execution_id"),
        status=parse_choice("status", DEFECT_STATUSES),
        severity=parse_choice("severity", DEFECT_SEVERITIES),
        priority=parse_choice("priority", DEFECT_PRIORITIES),
        component=parse_text("component"),
        assignee=parse_text("assignee"),
        keyword=parse_text("keyword"),
    )
    return jsonify(
        {
            "items": [
                serialize_defect(defect)
                for defect in pagination.items
            ],
            "pagination": serialize_pagination(pagination),
        }
    )


@bp.get("/defects/<int:defect_id>")
def defect_detail(defect_id):
    defect = DefectService.get_defect(defect_id)
    return jsonify(serialize_defect(defect, detail=True))


@bp.post("/defects")
def defect_create():
    request_model = require_json(DefectCreateRequest)
    defect = DefectService.create_defect(request_model.model_dump())
    response = jsonify(serialize_defect(defect, detail=True))
    response.status_code = 201
    response.headers["Location"] = url_for(
        "api_v1.defect_detail",
        defect_id=defect.id,
    )
    return response


@bp.patch("/defects/<int:defect_id>")
def defect_update(defect_id):
    request_model = require_json(DefectPatchRequest)
    defect = DefectService.update_defect(
        defect_id,
        request_model.model_dump(exclude_unset=True),
    )
    return jsonify(serialize_defect(defect, detail=True))
