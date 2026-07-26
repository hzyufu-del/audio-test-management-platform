from flask import current_app
from flask import jsonify

from app.extensions import db
from app.services.workflow_errors import WorkflowServiceError


class APIError(Exception):
    def __init__(self, code, message, status_code, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_response(code, message, status_code, details=None):
    response = jsonify(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        }
    )
    response.status_code = status_code
    return response


def register_error_handlers(blueprint):
    @blueprint.errorhandler(APIError)
    def handle_api_error(error):
        return error_response(
            error.code,
            error.message,
            error.status_code,
            error.details,
        )

    @blueprint.errorhandler(WorkflowServiceError)
    def handle_service_error(error):
        return error_response(
            error.code,
            error.message,
            error.status_code,
            error.details,
        )

    @blueprint.errorhandler(Exception)
    def handle_unexpected_error(error):
        db.session.rollback()
        current_app.logger.exception("Unhandled REST API V1 error")
        return error_response(
            "internal_error",
            "服务端无法完成请求。",
            500,
        )
