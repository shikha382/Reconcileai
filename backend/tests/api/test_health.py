def test_health_returns_ok(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "service": "reconcileai"}


def test_health_response_has_request_id_header(api_client):
    response = api_client.get("/health")
    assert "x-request-id" in {k.lower() for k in response.headers.keys()}
