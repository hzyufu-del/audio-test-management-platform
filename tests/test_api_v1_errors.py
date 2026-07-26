def test_unknown_api_route_returns_uniform_json_404(api_client):
    response = api_client.get("/api/v1/missing-resource")

    assert response.status_code == 404
    assert response.content_type == "application/json"
    assert response.get_json() == {
        "error": {
            "code": "not_found",
            "message": "资源不存在。",
            "details": {},
        }
    }


def test_non_json_write_returns_415(api_client):
    response = api_client.post(
        "/api/v1/test-cases",
        data={"title": "Sample form payload"},
    )

    assert response.status_code == 415
    assert response.get_json()["error"]["code"] == "unsupported_media_type"


def test_non_json_patch_returns_415(api_client):
    response = api_client.patch(
        "/api/v1/defects/1",
        data={"status": "fixed"},
    )

    assert response.status_code == 415
    assert response.get_json()["error"]["code"] == "unsupported_media_type"


def test_malformed_json_returns_400(api_client):
    response = api_client.post(
        "/api/v1/test-cases",
        data='{"version_id":',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "bad_request",
        "message": "JSON 格式无法解析。",
        "details": {},
    }


def test_non_object_json_root_returns_400(api_client):
    response = api_client.post("/api/v1/test-cases", json=[])

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "bad_request"


def test_empty_json_object_returns_422(api_client):
    response = api_client.post("/api/v1/test-cases", json={})

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"]["code"] == "validation_error"
    assert "version_id" in payload["error"]["details"]


def test_unknown_json_field_returns_422(api_client, api_catalog):
    response = api_client.post(
        "/api/v1/test-cases",
        json={
            "version_id": api_catalog["first_version_id"],
            "code": "TC_API_UNKNOWN",
            "title": "Sample unknown field test",
            "module": "Audio",
            "steps": "Run sample steps.",
            "expected_result": "Sample result is recorded.",
            "unexpected": "forbidden",
        },
    )

    assert response.status_code == 422
    assert "unexpected" in response.get_json()["error"]["details"]


def test_invalid_resource_identifier_returns_json_404(api_client):
    response = api_client.get("/api/v1/test-cases/not-an-id")

    assert response.status_code == 404
    assert response.content_type == "application/json"
    assert response.get_json()["error"]["code"] == "not_found"


def test_unexpected_server_error_is_safe(
    api_client,
    monkeypatch,
):
    from app.services.testcase_service import TestCaseService

    def fail_list(**_kwargs):
        raise RuntimeError(
            "sqlite:///private/path traceback secret internal config"
        )

    monkeypatch.setattr(TestCaseService, "list_test_cases", fail_list)
    response = api_client.get("/api/v1/test-cases")

    assert response.status_code == 500
    body = response.get_data(as_text=True)
    assert response.get_json()["error"] == {
        "code": "internal_error",
        "message": "服务端无法完成请求。",
        "details": {},
    }
    assert "traceback" not in body.lower()
    assert "private/path" not in body
    assert "internal config" not in body
