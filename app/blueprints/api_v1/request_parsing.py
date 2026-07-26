from datetime import datetime, timezone

from flask import request
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest

from .errors import APIError


VALIDATION_MESSAGES = {
    "missing": "字段不能为空。",
    "extra_forbidden": "不允许提供该字段。",
    "string_type": "字段必须是字符串。",
    "string_too_short": "字段不能为空。",
    "string_too_long": "字段长度超过限制。",
    "literal_error": "字段值不在允许范围内。",
    "int_type": "字段必须是整数。",
    "greater_than": "字段必须是正整数。",
    "datetime_type": "字段必须是 ISO-8601 日期时间。",
    "datetime_from_date_parsing": "日期时间格式无效。",
    "datetime_object_invalid": "日期时间格式无效。",
    "timezone_aware": "日期时间必须包含明确时区。",
    "value_error": "字段组合不符合业务规则。",
}


def require_json(schema_class):
    if request.mimetype != "application/json":
        raise APIError(
            "unsupported_media_type",
            "请求必须使用 application/json。",
            415,
        )

    try:
        payload = request.get_json(silent=False)
    except BadRequest as exc:
        raise APIError(
            "bad_request",
            "JSON 格式无法解析。",
            400,
        ) from exc

    if not isinstance(payload, dict):
        raise APIError(
            "bad_request",
            "JSON 根节点必须是 object。",
            400,
        )

    try:
        return schema_class.model_validate(payload)
    except ValidationError as exc:
        details = {}
        for error in exc.errors():
            location = error.get("loc") or ("_request",)
            field = str(location[0])
            message = VALIDATION_MESSAGES.get(
                error.get("type"),
                "字段值无效。",
            )
            details.setdefault(field, []).append(message)
        raise APIError(
            "validation_error",
            "请求参数校验失败。",
            422,
            details,
        ) from exc


def parse_pagination():
    page = parse_positive_int("page", default=1)
    page_size = parse_positive_int("page_size", default=20)
    if page_size > 100:
        raise APIError(
            "bad_request",
            "分页参数无效。",
            400,
            {"page_size": ["page_size 不能超过 100。"]},
        )
    return page, page_size


def parse_positive_int(name, default=None):
    raw_value = request.args.get(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise APIError(
            "bad_request",
            "查询参数格式无效。",
            400,
            {name: [f"{name} 必须是正整数。"]},
        ) from exc
    if value <= 0:
        raise APIError(
            "bad_request",
            "查询参数格式无效。",
            400,
            {name: [f"{name} 必须是正整数。"]},
        )
    return value


def parse_choice(name, allowed_values):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    if value not in allowed_values:
        raise APIError(
            "bad_request",
            "查询参数格式无效。",
            400,
            {name: [f"{name} 不在允许范围内。"]},
        )
    return value


def parse_text(name):
    value = request.args.get(name, "").strip()
    return value or None


def parse_aware_datetime(name):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise APIError(
            "bad_request",
            "日期时间查询参数无效。",
            400,
            {name: ["日期时间必须使用 ISO-8601 格式。"]},
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise APIError(
            "bad_request",
            "日期时间查询参数无效。",
            400,
            {name: ["日期时间必须包含明确时区。"]},
        )
    return parsed.astimezone(timezone.utc)
