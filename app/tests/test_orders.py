from app.config import settings


def test_create_order_standard(client):
    payload = {
        "customer_id": "cust-001",
        "customer_tier": "standard",
        "items": [{"item_id": "item-a", "quantity": 2, "unit_price": 50.0}],
    }
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["subtotal"] == 100.0
    assert data["discount_amount"] == 0.0
    assert data["total_amount"] == 100.0
    assert data["status"] == "confirmed"


def test_create_order_premium_discount(client):
    payload = {
        "customer_id": "cust-002",
        "customer_tier": "premium",
        "items": [{"item_id": "item-b", "quantity": 1, "unit_price": 200.0}],
    }
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["subtotal"] == 200.0
    assert data["discount_amount"] == 20.0  # 10% discount
    assert data["total_amount"] == 180.0


def test_get_order_by_id(client):
    # First create
    create_payload = {
        "customer_id": "cust-003",
        "customer_tier": "enterprise",
        "items": [{"item_id": "item-c", "quantity": 10, "unit_price": 10.0}],
    }
    create_res = client.post("/api/v1/orders", json=create_payload)
    order_id = create_res.json()["id"]

    get_res = client.get(f"/api/v1/orders/{order_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == order_id
    assert get_res.json()["discount_amount"] == 20.0  # 20% discount


def test_get_nonexistent_order(client):
    response = client.get("/api/v1/orders/ord-nonexistent")
    assert response.status_code == 404


def test_fault_injection_triggers_500(client):
    # Enable fault injection
    settings.fault_injection_mode = True
    try:
        payload = {
            "customer_id": "cust-fault-test",
            "customer_tier": "standard",
            "items": [{"item_id": "item-fault", "quantity": 1, "unit_price": 10.0}],
        }
        response = client.post("/api/v1/orders", json=payload)
        assert response.status_code == 500
        assert "Internal discount calculation fault" in response.json()["detail"]
    finally:
        # Reset back to healthy
        settings.fault_injection_mode = False
