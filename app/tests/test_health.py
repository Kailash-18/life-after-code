def test_healthz_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["fault_injection_active"] is False


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_metrics_reflect_requests_and_errors(client):
    from app.config import settings

    # 1. Successful request
    client.get("/api/v1/orders")
    res1 = client.get("/metrics")
    assert 'endpoint="/api/v1/orders"' in res1.text

    # 2. Injected error request
    settings.fault_injection_mode = True
    try:
        client.post(
            "/api/v1/orders",
            json={
                "customer_id": "cust-m",
                "customer_tier": "standard",
                "items": [{"item_id": "i-1", "quantity": 1, "unit_price": 10.0}],
            },
        )
    finally:
        settings.fault_injection_mode = False

    res2 = client.get("/metrics")
    assert 'http_errors_total{endpoint="/api/v1/orders",status_code="500"}' in res2.text
