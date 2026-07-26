from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import TestCase as ChecklistTestCase
from app.models import TestExecution as ExecutionRecord


def valid_execution_payload(test_case_id, **overrides):
    payload = {
        "test_case_id": test_case_id,
        "result": "failed",
        "actual_result": "Sample device did not reconnect.",
        "tester": "API Demo Tester",
        "environment": "Android Sample Env",
        "executed_at": "2026-07-26T10:30:00+00:00",
        "notes": "Created through REST API V1.",
    }
    payload.update(overrides)
    return payload


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    assert response.content_type == "application/json"
    payload = response.get_json()
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["details"], dict)
    return payload["error"]


def test_execution_list_returns_stable_order_and_defect_counts(
    api_client, api_executions
):
    response = api_client.get("/api/v1/executions")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["items"]] == [
        api_executions["blocked_id"],
        api_executions["failed_id"],
        api_executions["passed_id"],
    ]
    failed = payload["items"][1]
    assert failed["test_case_code"] == "TC_BT_API_002"
    assert failed["test_case_title"] == "Demo Bluetooth Reconnect API Case"
    assert failed["has_defects"] is True
    assert failed["defect_count"] == 1
    assert payload["pagination"]["total"] == 3


@pytest.mark.parametrize(
    ("query", "expected_key"),
    [
        ("project_id={first_project_id}", "failed_id"),
        ("version_id={first_version_id}", "failed_id"),
        ("test_case_id={first_case_id}", "passed_id"),
        ("result=blocked", "blocked_id"),
        ("tester=Demo API Tester A", "passed_id"),
        ("environment=Firmware Demo Env", "blocked_id"),
        ("executed_from=2026-07-22T00:00:00Z", "blocked_id"),
        ("executed_to=2026-07-20T23:59:59Z", "passed_id"),
    ],
)
def test_execution_list_supports_filters(
    api_client,
    api_catalog,
    api_executions,
    query,
    expected_key,
):
    response = api_client.get(
        f"/api/v1/executions?{query.format(**api_catalog)}"
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.get_json()["items"]]
    assert api_executions[expected_key] in ids


@pytest.mark.parametrize(
    "query",
    [
        "page=zero",
        "page_size=101",
        "project_id=-1",
        "version_id=abc",
        "test_case_id=0",
        "result=unknown",
        "executed_from=not-a-date",
        "executed_to=2026-07-26T10:30:00",
        (
            "executed_from=2026-07-27T00:00:00Z"
            "&executed_to=2026-07-26T00:00:00Z"
        ),
    ],
)
def test_execution_list_rejects_invalid_filters(
    api_client, api_executions, query
):
    response = api_client.get(f"/api/v1/executions?{query}")

    assert_error(response, 400, "bad_request")


def test_execution_detail_returns_historical_snapshots_and_defects(
    api_client, api_executions
):
    response = api_client.get(
        f"/api/v1/executions/{api_executions['failed_id']}"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["test_case_code_snapshot"] == "TC_BT_API_002"
    assert (
        payload["test_case_title_snapshot"]
        == "Demo Bluetooth Reconnect API Case"
    )
    assert payload["steps_snapshot"] == "Run demo reconnect steps."
    assert payload["duration_seconds"] is None
    assert payload["external_case_key"] is None
    assert payload["test_run_id"] is None
    assert payload["defects"] == [
        {
            "id": api_executions["defect_id"],
            "code": "DEF_API_EXECUTION_SUMMARY",
            "title": "Sample execution summary defect",
            "status": "open",
            "severity": "major",
        }
    ]


def test_execution_detail_returns_uniform_404(api_client):
    response = api_client.get("/api/v1/executions/999999")

    assert_error(response, 404, "not_found")


def test_execution_detail_serializes_decimal_duration(
    api_client,
    api_app,
    api_executions,
):
    with api_app.app_context():
        execution = db.session.get(
            ExecutionRecord,
            api_executions["passed_id"],
        )
        execution.duration_seconds = Decimal("1.234")
        db.session.commit()

    response = api_client.get(
        f"/api/v1/executions/{api_executions['passed_id']}"
    )

    assert response.status_code == 200
    assert response.get_json()["duration_seconds"] == 1.234


@pytest.mark.parametrize(
    ("result", "actual_result", "notes"),
    [
        ("passed", None, None),
        ("failed", "Sample failure recorded.", None),
        ("blocked", None, "Mock fixture unavailable."),
    ],
)
def test_execution_create_supports_manual_results(
    api_client,
    api_app,
    api_catalog,
    result,
    actual_result,
    notes,
):
    response = api_client.post(
        "/api/v1/executions",
        json=valid_execution_payload(
            api_catalog["first_case_id"],
            result=result,
            actual_result=actual_result,
            notes=notes,
        ),
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert response.headers["Location"].endswith(
        f"/api/v1/executions/{payload['id']}"
    )
    assert payload["result"] == result
    assert payload["test_run_id"] is None
    assert payload["external_case_key"] is None
    assert payload["duration_seconds"] is None

    with api_app.app_context():
        saved = db.session.get(ExecutionRecord, payload["id"])
        assert saved.test_case_id == api_catalog["first_case_id"]


def test_execution_create_uses_server_time_when_omitted(
    api_client, api_catalog
):
    before = datetime.now(timezone.utc)
    payload = valid_execution_payload(
        api_catalog["first_case_id"],
        result="passed",
        actual_result=None,
    )
    payload.pop("executed_at")

    response = api_client.post("/api/v1/executions", json=payload)
    after = datetime.now(timezone.utc)

    assert response.status_code == 201
    executed_at = datetime.fromisoformat(
        response.get_json()["executed_at"].replace("Z", "+00:00")
    )
    assert before <= executed_at <= after


def test_execution_create_captures_snapshot_that_survives_test_case_changes(
    api_client, api_app, api_catalog
):
    response = api_client.post(
        "/api/v1/executions",
        json=valid_execution_payload(api_catalog["first_case_id"]),
    )
    execution_id = response.get_json()["id"]

    with api_app.app_context():
        test_case = db.session.get(
            ChecklistTestCase,
            api_catalog["first_case_id"],
        )
        test_case.code = "TC_CHANGED_AFTER_API_EXECUTION"
        test_case.title = "Changed live TestCase title"
        test_case.steps = "Changed live steps."
        db.session.commit()

    detail = api_client.get(f"/api/v1/executions/{execution_id}").get_json()
    assert detail["test_case_code_snapshot"] == "TC_AUDIO_API_001"
    assert detail["test_case_title_snapshot"] == "Sample Audio Playback API Case"
    assert detail["steps_snapshot"] == "Run sample playback steps."


def test_execution_create_returns_404_for_missing_test_case(api_client):
    response = api_client.post(
        "/api/v1/executions",
        json=valid_execution_payload(999999),
    )

    assert_error(response, 404, "not_found")


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"result": "unknown"}, "result"),
        ({"tester": " "}, "tester"),
        ({"result": "failed", "actual_result": ""}, "_request"),
        (
            {"result": "blocked", "actual_result": None, "notes": None},
            "_request",
        ),
        ({"executed_at": "not-a-date"}, "executed_at"),
        ({"executed_at": "2026-07-26T10:30:00"}, "executed_at"),
        ({"test_case_code_snapshot": "FORBIDDEN"}, "test_case_code_snapshot"),
        ({"test_run_id": 10}, "test_run_id"),
    ],
)
def test_execution_create_rejects_invalid_or_forbidden_fields(
    api_client, api_catalog, overrides, field
):
    response = api_client.post(
        "/api/v1/executions",
        json=valid_execution_payload(
            api_catalog["first_case_id"],
            **overrides,
        ),
    )

    error = assert_error(response, 422, "validation_error")
    assert field in error["details"]


def test_execution_create_rolls_back_database_failure(
    api_client, api_app, api_catalog, monkeypatch
):
    def fail_commit():
        raise SQLAlchemyError("private database path and SQL details")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = api_client.post(
        "/api/v1/executions",
        json=valid_execution_payload(api_catalog["first_case_id"]),
    )

    error = assert_error(response, 500, "internal_error")
    assert error["details"] == {}
    assert "private database" not in response.get_data(as_text=True)

    with api_app.app_context():
        assert (
            ExecutionRecord.query.filter_by(tester="API Demo Tester").count()
            == 0
        )
