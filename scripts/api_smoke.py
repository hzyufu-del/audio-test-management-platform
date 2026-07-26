#!/usr/bin/env python3
import argparse
import json
import socket
import sys
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:5000"
DEFAULT_TIMEOUT = 5.0


class SmokeError(Exception):
    """A safe, user-facing smoke workflow failure."""


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return timeout


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the REST API V1 mock/demo/sample smoke workflow."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Application base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT:g})",
    )
    return parser


def normalize_base_url(value):
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SmokeError("base URL must use http or https and include a host")
    if parsed.username or parsed.password:
        raise SmokeError("base URL must not contain credentials")
    return base_url


def decode_json_response(method, url, status, headers, body):
    content_type = headers.get_content_type()
    if content_type != "application/json":
        raise SmokeError(
            f"{method} {url} returned {status} with a non-JSON response"
        )
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeError(
            f"{method} {url} returned {status} with invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise SmokeError(
            f"{method} {url} returned {status} with a non-object JSON body"
        )
    return payload


def api_error_message(method, url, status, payload):
    error = payload.get("error")
    if not isinstance(error, dict):
        return f"{method} {url} returned HTTP {status}"
    code = str(error.get("code") or "api_error")
    message = str(error.get("message") or "request failed")
    return f"{method} {url} returned HTTP {status} ({code}): {message}"


def request_json(method, url, timeout, payload=None, expected_status=200):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            response_headers = response.headers
            response_body = response.read()
    except HTTPError as exc:
        response_body = exc.read()
        response_headers = exc.headers
        if response_headers.get_content_type() != "application/json":
            raise SmokeError(
                f"{method} {url} returned HTTP {exc.code} "
                "with a non-JSON response"
            ) from exc
        error_payload = decode_json_response(
            method,
            url,
            exc.code,
            response_headers,
            response_body,
        )
        raise SmokeError(
            api_error_message(method, url, exc.code, error_payload)
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise SmokeError(f"{method} {url} timed out") from exc
    except (URLError, OSError) as exc:
        raise SmokeError(
            f"{method} {url} is unavailable or refused the connection"
        ) from exc

    response_payload = decode_json_response(
        method,
        url,
        status,
        response_headers,
        response_body,
    )
    if status != expected_status:
        raise SmokeError(
            api_error_message(method, url, status, response_payload)
        )
    return status, response_headers, response_payload


def positive_id(payload, name):
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SmokeError(f"response field {name} must be a positive integer")
    return value


def print_step(stream, label, method, url, status, summary):
    print(f"{label}: {method} {url} [{status}] {summary}", file=stream)


def require_location(headers, resource_path):
    location = headers.get("Location", "")
    if not location.endswith(resource_path):
        raise SmokeError("created resource response is missing Location")


def run_smoke(base_url, timeout=DEFAULT_TIMEOUT, stream=sys.stdout):
    base_url = normalize_base_url(base_url)
    api_url = f"{base_url}/api/v1"
    unique_suffix = (
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        + uuid.uuid4().hex[:6].upper()
    )

    health_url = f"{api_url}/health"
    status, _, health = request_json(
        "GET",
        health_url,
        timeout,
        expected_status=200,
    )
    if health.get("status") != "ok":
        raise SmokeError("health response did not report status=ok")
    print_step(
        stream,
        "Health",
        "GET",
        health_url,
        status,
        f"service={health.get('service')} status={health.get('status')}",
    )

    list_url = f"{api_url}/test-cases?page=1&page_size=1"
    status, _, test_case_list = request_json(
        "GET",
        list_url,
        timeout,
        expected_status=200,
    )
    items = test_case_list.get("items")
    if not isinstance(items, list) or not items:
        raise SmokeError(
            "demo TestCase list is empty; run flask --app run.py init-db"
        )
    version_id = positive_id(items[0], "version_id")
    print_step(
        stream,
        "Demo Version",
        "GET",
        list_url,
        status,
        f"version_id={version_id}",
    )

    test_case_url = f"{api_url}/test-cases"
    test_case_code = f"TC_SMOKE_{unique_suffix}"
    status, headers, test_case = request_json(
        "POST",
        test_case_url,
        timeout,
        payload={
            "version_id": version_id,
            "code": test_case_code,
            "title": "Sample REST API smoke TestCase",
            "module": "Audio",
            "priority": "P2",
            "case_type": "checklist",
            "precondition": "Use mock device state only.",
            "steps": "Run the sample audio smoke workflow.",
            "expected_result": "The sample API workflow records the result.",
            "status": "draft",
        },
        expected_status=201,
    )
    test_case_id = positive_id(test_case, "id")
    require_location(headers, f"/api/v1/test-cases/{test_case_id}")
    print_step(
        stream,
        "Create TestCase",
        "POST",
        test_case_url,
        status,
        f"id={test_case_id} code={test_case.get('code')}",
    )

    execution_url = f"{api_url}/executions"
    status, headers, execution = request_json(
        "POST",
        execution_url,
        timeout,
        payload={
            "test_case_id": test_case_id,
            "result": "failed",
            "actual_result": "Sample smoke failure for defect creation.",
            "tester": "API Smoke Demo Tester",
            "environment": "Local Demo Environment",
            "notes": "Created by the standard-library smoke script.",
        },
        expected_status=201,
    )
    execution_id = positive_id(execution, "id")
    require_location(headers, f"/api/v1/executions/{execution_id}")
    print_step(
        stream,
        "Create Execution",
        "POST",
        execution_url,
        status,
        f"id={execution_id} result={execution.get('result')}",
    )

    defect_url = f"{api_url}/defects"
    defect_code = f"DEF_SMOKE_{unique_suffix}"
    status, headers, defect = request_json(
        "POST",
        defect_url,
        timeout,
        payload={
            "test_execution_id": execution_id,
            "code": defect_code,
            "title": "Sample REST API smoke defect",
            "description": "Mock defect created by the API smoke workflow.",
            "component": "Audio",
            "severity": "major",
            "priority": "P2",
            "status": "open",
            "reproduction_steps": "Run the sample API smoke steps.",
            "observed_result": "The mock execution records a sample failure.",
            "reporter": "API Smoke Demo Tester",
            "assignee": None,
        },
        expected_status=201,
    )
    defect_id = positive_id(defect, "id")
    require_location(headers, f"/api/v1/defects/{defect_id}")
    print_step(
        stream,
        "Create Defect",
        "POST",
        defect_url,
        status,
        f"id={defect_id} code={defect.get('code')}",
    )

    defect_detail_url = f"{api_url}/defects/{defect_id}"
    status, _, defect = request_json(
        "PATCH",
        defect_detail_url,
        timeout,
        payload={
            "status": "fixed",
            "resolution": "sample_smoke_fix",
            "resolution_note": "Verified by the local demo smoke workflow.",
        },
        expected_status=200,
    )
    print_step(
        stream,
        "Patch Defect",
        "PATCH",
        defect_detail_url,
        status,
        f"id={defect_id} status={defect.get('status')}",
    )

    readbacks = (
        (
            "Read TestCase",
            f"{api_url}/test-cases/{test_case_id}",
            test_case_id,
        ),
        (
            "Read Execution",
            f"{api_url}/executions/{execution_id}",
            execution_id,
        ),
        ("Read Defect", defect_detail_url, defect_id),
    )
    for label, resource_url, resource_id in readbacks:
        status, _, resource = request_json(
            "GET",
            resource_url,
            timeout,
            expected_status=200,
        )
        if positive_id(resource, "id") != resource_id:
            raise SmokeError(f"{label} returned a different resource id")
        print_step(
            stream,
            label,
            "GET",
            resource_url,
            status,
            f"id={resource_id}",
        )

    print("REST API V1 smoke workflow passed.", file=stream)
    return {
        "version_id": version_id,
        "test_case_id": test_case_id,
        "execution_id": execution_id,
        "defect_id": defect_id,
    }


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run_smoke(args.base_url, timeout=args.timeout)
    except SmokeError as exc:
        print(f"Smoke failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Smoke failed: unexpected local error; rerun after checking "
            "the demo service.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
