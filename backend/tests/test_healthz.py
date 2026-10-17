def test_backend_healthz(client):
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "sentinel-backend"
    assert "version" in data


def test_root_route(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["health"] == "/api/v1/healthz"
    assert data["status"] == "/api/v1/status"
