import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import TestCase as ChecklistTestCase


def valid_test_case_payload(version_id, **overrides):
    payload = {
        "version_id": version_id,
        "code": "TC_API_CREATE_001",
        "title": "Sample API TestCase",
        "module": "Audio",
        "priority": "P1",
        "case_type": "checklist",
        "precondition": "Use mock device state.",
        "steps": "Run sample API steps.",
        "expected_result": "The sample result is recorded.",
        "status": "draft",
    }
    payload.update(overrides)
    return payload


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    assert response.content_type == "application/json"
    payload = response.get_json()
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert isinstance(payload["error"]["details"], dict)
    return payload["error"]


def test_test_case_list_uses_default_pagination_and_stable_order(
    api_client, api_catalog
):
    response = api_client.get("/api/v1/test-cases")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["code"] for item in payload["items"]] == [
        "TC_CHARGING_API_003",
        "TC_BT_API_002",
        "TC_AUDIO_API_001",
    ]
    assert payload["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 3,
        "pages": 1,
    }
    first = payload["items"][0]
    assert first["version_code"] == "FW_SAMPLE_API_GAMMA"
    assert first["project_code"] == "DEMO-API-SECONDARY"
    assert first["created_at"].endswith("Z")
    assert first["updated_at"].endswith("Z")


@pytest.mark.parametrize(
    ("query", "expected_codes"),
    [
        ("project_id={first_project_id}", ["TC_BT_API_002", "TC_AUDIO_API_001"]),
        ("version_id={first_version_id}", ["TC_BT_API_002", "TC_AUDIO_API_001"]),
        ("module=Audio", ["TC_AUDIO_API_001"]),
        ("priority=P2", ["TC_BT_API_002"]),
        ("status=archived", ["TC_CHARGING_API_003"]),
        ("keyword=reconnect", ["TC_BT_API_002"]),
        ("keyword=TC_AUDIO", ["TC_AUDIO_API_001"]),
    ],
)
def test_test_case_list_supports_filters(
    api_client, api_catalog, query, expected_codes
):
    response = api_client.get(
        f"/api/v1/test-cases?{query.format(**api_catalog)}"
    )

    assert response.status_code == 200
    assert [item["code"] for item in response.get_json()["items"]] == expected_codes


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=abc",
        "page_size=0",
        "page_size=101",
        "project_id=0",
        "project_id=abc",
        "version_id=-1",
    ],
)
def test_test_case_list_rejects_invalid_numeric_filters(
    api_client, api_catalog, query
):
    response = api_client.get(f"/api/v1/test-cases?{query}")

    assert_error(response, 400, "bad_request")


def test_test_case_list_reports_pagination_and_empty_pages(api_client, api_catalog):
    first_page = api_client.get("/api/v1/test-cases?page=1")
    second_page = api_client.get("/api/v1/test-cases?page=2&page_size=1")
    empty_page = api_client.get("/api/v1/test-cases?page=4&page_size=1")
    max_page_size = api_client.get("/api/v1/test-cases?page_size=100")

    assert first_page.get_json()["pagination"]["page"] == 1
    assert [item["code"] for item in second_page.get_json()["items"]] == [
        "TC_BT_API_002"
    ]
    assert second_page.get_json()["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 3,
        "pages": 3,
    }
    assert empty_page.get_json()["items"] == []
    assert empty_page.get_json()["pagination"]["total"] == 3
    assert max_page_size.get_json()["pagination"]["page_size"] == 100


def test_test_case_detail_returns_full_resource(api_client, api_catalog):
    response = api_client.get(
        f"/api/v1/test-cases/{api_catalog['first_case_id']}"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "TC_AUDIO_API_001"
    assert payload["precondition"] == "Use mock audio state."
    assert payload["steps"] == "Run sample playback steps."
    assert payload["expected_result"] == "Sample playback succeeds."


def test_test_case_detail_returns_uniform_404(api_client):
    response = api_client.get("/api/v1/test-cases/999999")

    assert_error(response, 404, "not_found")


def test_test_case_create_returns_201_location_and_trimmed_resource(
    api_client, api_app, api_catalog
):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["first_version_id"],
            code="  TC_API_TRIMMED  ",
            title="  Sample trimmed TestCase  ",
        ),
    )

    assert response.status_code == 201
    assert response.headers["Location"].endswith(
        f"/api/v1/test-cases/{response.get_json()['id']}"
    )
    assert response.get_json()["code"] == "TC_API_TRIMMED"
    assert response.get_json()["title"] == "Sample trimmed TestCase"

    with api_app.app_context():
        saved = db.session.get(ChecklistTestCase, response.get_json()["id"])
        assert saved.version_id == api_catalog["first_version_id"]
        assert saved.case_type == "checklist"


def test_test_case_create_returns_404_for_missing_version(api_client):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(999999),
    )

    assert_error(response, 404, "not_found")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", "   "),
        ("title", ""),
        ("module", ""),
        ("steps", " "),
        ("expected_result", ""),
        ("priority", "P9"),
        ("case_type", "automation"),
        ("status", "paused"),
    ],
)
def test_test_case_create_rejects_invalid_fields(
    api_client, api_catalog, field, value
):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["first_version_id"],
            **{field: value},
        ),
    )

    error = assert_error(response, 422, "validation_error")
    assert field in error["details"]


@pytest.mark.parametrize("forbidden_field", ["id", "created_at", "updated_at"])
def test_test_case_create_rejects_client_managed_and_unknown_fields(
    api_client, api_catalog, forbidden_field
):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["first_version_id"],
            **{forbidden_field: 1},
        ),
    )

    error = assert_error(response, 422, "validation_error")
    assert forbidden_field in error["details"]


def test_test_case_create_returns_409_for_duplicate_code_in_same_version(
    api_client, api_catalog
):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["first_version_id"],
            code="TC_AUDIO_API_001",
        ),
    )

    assert_error(response, 409, "conflict")


def test_test_case_create_allows_same_code_in_different_version(
    api_client, api_catalog
):
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["second_version_id"],
            code="TC_AUDIO_API_001",
        ),
    )

    assert response.status_code == 201
    assert response.get_json()["version_id"] == api_catalog["second_version_id"]


def test_test_case_create_rolls_back_database_failure_without_leaking_details(
    api_client, api_app, api_catalog, monkeypatch
):
    def fail_commit():
        raise SQLAlchemyError(
            "sqlite:///private/path.sqlite INSERT INTO test_case secret"
        )

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = api_client.post(
        "/api/v1/test-cases",
        json=valid_test_case_payload(
            api_catalog["first_version_id"],
            code="TC_API_ROLLBACK",
        ),
    )

    error = assert_error(response, 500, "internal_error")
    serialized = response.get_data(as_text=True)
    assert "private/path" not in serialized
    assert "INSERT INTO" not in serialized
    assert "SQLAlchemyError" not in serialized
    assert error["details"] == {}

    with api_app.app_context():
        assert ChecklistTestCase.query.filter_by(code="TC_API_ROLLBACK").count() == 0
