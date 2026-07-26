def test_health_returns_public_service_metadata(api_client):
    response = api_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.content_type == "application/json"
    assert response.get_json() == {
        "status": "ok",
        "service": "audio-test-management-platform",
        "api_version": "v1",
    }
