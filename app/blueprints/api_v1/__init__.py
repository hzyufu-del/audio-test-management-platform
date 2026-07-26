from flask import Blueprint

from .errors import register_error_handlers


bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

register_error_handlers(bp)

from . import defects, executions, routes, testcases  # noqa: E402, F401
