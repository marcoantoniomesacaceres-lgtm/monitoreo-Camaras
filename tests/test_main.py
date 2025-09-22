import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app, CAMERA_ACTIVE

client = TestClient(app)


# ------------------------
# ✅ Test /health
# ------------------------
def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ------------------------
# ✅ Test /status
# ------------------------
def test_status_endpoint():
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "state" in data
    assert "camera_active" in data
    assert "camera_status" in data


# ------------------------
# ✅ Test /durations (mock DB)
# ------------------------
@patch("main.storage.get_person_durations")
def test_durations_with_mock(mock_db):
    mock_db.return_value = [{"person_id": 1, "duration": 120}]
    response = client.get("/durations")
    assert response.status_code == 200
    assert response.json()[0]["person_id"] == 1
    assert response.json()[0]["duration"] == 120


# ------------------------
# ✅ Test /toggle_camera (mock cámara)
# ------------------------
@patch("main.notifications.notify")
def test_toggle_camera(mock_notify):
    # Estado inicial
    response = client.post("/toggle_camera")
    assert response.status_code == 200
    data = response.json()
    assert "camera_active" in data
    assert "camera_status" in data

    # Verifica que la notificación fue llamada
    mock_notify.assert_called()


# ------------------------
# ✅ Test /readiness
# ------------------------
@patch("main.storage.get_stats")
def test_readiness_ok(mock_stats):
    mock_stats.return_value = {"ok": True}
    response = client.get("/readiness")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"