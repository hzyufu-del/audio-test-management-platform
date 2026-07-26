import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Defect
from app.models import TestExecution as ExecutionRecord


def valid_defect_payload(execution_id, **overrides):
    payload = {
        "test_execution_id": execution_id,
        "code": "DEF_API_CREATE_001",
        "title": "Sample reconnect defect",
        "description": "Reconnect failed in the sample environment.",
        "component": "Bluetooth",
        "severity": "major",
        "priority": "P1",
        "status": "open",
        "reproduction_steps": "Run the sample reconnect scenario.",
        "observed_result": "The mock device remained disconnected.",
        "reporter": "API Demo Tester",
        "assignee": None,
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


def test_defect_list_returns_stable_order_and_snapshot_summary(
    api_client, api_defects
):
    response = api_client.get("/api/v1/defects")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["items"]] == [
        api_defects["rejected_id"],
        api_defects["fixed_id"],
        api_defects["open_id"],
    ]
    assert payload["items"][0]["test_case_code"] == "TC_CHARGING_API_003"
    assert payload["pagination"]["total"] == 3


@pytest.mark.parametrize(
    ("query", "expected_key"),
    [
        ("project_id={first_project_id}", "fixed_id"),
        ("version_id={first_version_id}", "fixed_id"),
        ("test_execution_id={other_failed_id}", "rejected_id"),
        ("status=fixed", "fixed_id"),
        ("severity=minor", "rejected_id"),
        ("priority=P0", "fixed_id"),
        ("component=Charging", "rejected_id"),
        ("assignee=Sample API Assignee", "fixed_id"),
        ("keyword=fixed reconnect", "fixed_id"),
        ("keyword=DEF_API_REJECTED", "rejected_id"),
        ("keyword=cross-project", "rejected_id"),
    ],
)
def test_defect_list_supports_filters(
    api_client,
    api_catalog,
    api_defects,
    query,
    expected_key,
):
    response = api_client.get(
        f"/api/v1/defects?{query.format(**api_catalog, **api_defects)}"
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.get_json()["items"]]
    assert api_defects[expected_key] in ids


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=101",
        "project_id=abc",
        "version_id=-1",
        "test_execution_id=0",
        "status=unknown",
        "severity=medium",
        "priority=P9",
    ],
)
def test_defect_list_rejects_invalid_filters(
    api_client, api_defects, query
):
    response = api_client.get(f"/api/v1/defects?{query}")

    assert_error(response, 400, "bad_request")


def test_defect_detail_returns_snapshots_and_relationship_summaries(
    api_client, api_defects
):
    response = api_client.get(
        f"/api/v1/defects/{api_defects['open_id']}"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "DEF_API_EXECUTION_SUMMARY"
    assert payload["description"] == "Mock defect used by execution detail tests."
    assert payload["environment_snapshot"] == "Android Sample Env"
    assert (
        payload["actual_result_snapshot"]
        == "Sample reconnect remained unavailable."
    )
    assert payload["executed_at_snapshot"].endswith("Z")
    assert payload["execution"]["result"] == "failed"
    assert payload["test_case"] == {
        "id": payload["execution"]["test_case_id"],
        "code": "TC_BT_API_002",
        "title": "Demo Bluetooth Reconnect API Case",
    }


def test_defect_detail_returns_uniform_404(api_client):
    response = api_client.get("/api/v1/defects/999999")

    assert_error(response, 404, "not_found")


def test_defect_create_from_failed_execution_returns_201_and_location(
    api_client, api_app, api_executions
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(
            api_executions["failed_id"],
            code="  def_api_trimmed  ",
            title="  Sample trimmed defect  ",
        ),
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert response.headers["Location"].endswith(
        f"/api/v1/defects/{payload['id']}"
    )
    assert payload["code"] == "DEF_API_TRIMMED"
    assert payload["title"] == "Sample trimmed defect"

    with api_app.app_context():
        saved = db.session.get(Defect, payload["id"])
        source = db.session.get(
            ExecutionRecord,
            api_executions["failed_id"],
        )
        assert saved.environment_snapshot == source.environment
        assert saved.actual_result_snapshot == source.actual_result
        assert saved.executed_at_snapshot == source.executed_at


@pytest.mark.parametrize("execution_key", ["passed_id", "blocked_id"])
def test_defect_create_rejects_non_failed_execution(
    api_client, api_executions, execution_key
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(api_executions[execution_key]),
    )

    assert_error(response, 409, "conflict")


def test_defect_create_returns_404_for_missing_execution(api_client):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(999999),
    )

    assert_error(response, 404, "not_found")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", " "),
        ("title", ""),
        ("description", ""),
        ("component", " "),
        ("reproduction_steps", ""),
        ("observed_result", ""),
        ("reporter", " "),
        ("severity", "medium"),
        ("priority", "P9"),
        ("status", "triaged"),
    ],
)
def test_defect_create_rejects_invalid_fields(
    api_client, api_executions, field, value
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(
            api_executions["failed_id"],
            **{field: value},
        ),
    )

    error = assert_error(response, 422, "validation_error")
    assert field in error["details"]


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "id",
        "created_at",
        "updated_at",
        "environment_snapshot",
        "actual_result_snapshot",
        "executed_at_snapshot",
    ],
)
def test_defect_create_rejects_managed_and_snapshot_fields(
    api_client, api_executions, forbidden_field
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(
            api_executions["failed_id"],
            **{forbidden_field: "FORBIDDEN"},
        ),
    )

    error = assert_error(response, 422, "validation_error")
    assert forbidden_field in error["details"]


def test_defect_create_returns_409_for_duplicate_code(
    api_client, api_executions
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(
            api_executions["failed_id"],
            code="DEF_API_EXECUTION_SUMMARY",
        ),
    )

    assert_error(response, 409, "conflict")


def test_defect_snapshot_survives_execution_changes(
    api_client, api_app, api_executions
):
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(api_executions["failed_id"]),
    )
    defect_id = response.get_json()["id"]

    with api_app.app_context():
        execution = db.session.get(
            ExecutionRecord,
            api_executions["failed_id"],
        )
        execution.environment = "Changed live environment"
        execution.actual_result = "Changed live actual result."
        db.session.commit()

    detail = api_client.get(f"/api/v1/defects/{defect_id}").get_json()
    assert detail["environment_snapshot"] == "Android Sample Env"
    assert (
        detail["actual_result_snapshot"]
        == "Sample reconnect remained unavailable."
    )


def test_defect_patch_updates_only_workflow_fields(
    api_client, api_app, api_defects
):
    response = api_client.patch(
        f"/api/v1/defects/{api_defects['open_id']}",
        json={
            "status": "fixed",
            "severity": "critical",
            "priority": "P0",
            "assignee": "  Sample Resolver  ",
            "resolution": "  firmware_update  ",
            "resolution_note": "  Sample resolution verified.  ",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "fixed"
    assert payload["severity"] == "critical"
    assert payload["priority"] == "P0"
    assert payload["assignee"] == "Sample Resolver"
    assert payload["resolution"] == "firmware_update"

    with api_app.app_context():
        saved = db.session.get(Defect, api_defects["open_id"])
        assert saved.code == "DEF_API_EXECUTION_SUMMARY"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"code": "DEF_FORBIDDEN"},
        {"test_execution_id": 999},
        {"environment_snapshot": "FORBIDDEN"},
        {"status": "unknown"},
        {"status": None},
        {"severity": "medium"},
        {"severity": None},
        {"priority": "P9"},
        {"priority": None},
    ],
)
def test_defect_patch_rejects_empty_unknown_forbidden_and_invalid_fields(
    api_client, api_defects, payload
):
    response = api_client.patch(
        f"/api/v1/defects/{api_defects['open_id']}",
        json=payload,
    )

    assert_error(response, 422, "validation_error")


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "fixed"},
        {"status": "closed"},
        {"status": "rejected"},
        {"status": "open", "resolution": "unexpected_resolution"},
    ],
)
def test_defect_patch_rejects_business_state_conflicts(
    api_client, api_defects, payload
):
    response = api_client.patch(
        f"/api/v1/defects/{api_defects['open_id']}",
        json=payload,
    )

    assert_error(response, 409, "conflict")


def test_defect_patch_returns_uniform_404(api_client):
    response = api_client.patch(
        "/api/v1/defects/999999",
        json={"assignee": "Sample Resolver"},
    )

    assert_error(response, 404, "not_found")


def test_defect_create_rolls_back_database_failure(
    api_client, api_app, api_executions, monkeypatch
):
    def fail_commit():
        raise SQLAlchemyError("private SQL failure details")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = api_client.post(
        "/api/v1/defects",
        json=valid_defect_payload(
            api_executions["failed_id"],
            code="DEF_API_ROLLBACK_CREATE",
        ),
    )

    assert_error(response, 500, "internal_error")
    assert "private SQL" not in response.get_data(as_text=True)
    with api_app.app_context():
        assert Defect.query.filter_by(code="DEF_API_ROLLBACK_CREATE").count() == 0


def test_defect_patch_rolls_back_database_failure(
    api_client, api_app, api_defects, monkeypatch
):
    def fail_commit():
        raise SQLAlchemyError("private update failure details")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = api_client.patch(
        f"/api/v1/defects/{api_defects['open_id']}",
        json={"assignee": "Rollback Assignee"},
    )

    assert_error(response, 500, "internal_error")
    with api_app.app_context():
        saved = db.session.get(Defect, api_defects["open_id"])
        assert saved.assignee is None
