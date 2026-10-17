from app.config import settings


def test_get_status(client):
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "current_release" in data
    assert "traffic_split" in data
    assert "system_health" in data


def test_get_releases(client):
    response = client.get("/api/v1/releases")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["id"] == "rel-stable-initial"


def test_gitlab_webhook_unauthorized(client):
    response = client.post(
        "/api/v1/webhooks/gitlab",
        json={"object_kind": "pipeline"},
        headers={"X-Gitlab-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_gitlab_webhook_authorized(client):
    response = client.post(
        "/api/v1/webhooks/gitlab",
        json={"object_kind": "pipeline", "status": "success"},
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
