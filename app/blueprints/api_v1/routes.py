from flask import jsonify

from . import bp
from .errors import error_response


@bp.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "audio-test-management-platform",
            "api_version": "v1",
        }
    )


@bp.route(
    "/<path:_unmatched_path>",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
)
def not_found(_unmatched_path):
    return error_response("not_found", "资源不存在。", 404)
