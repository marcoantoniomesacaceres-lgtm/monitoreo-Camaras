import pytest
from fastapi.testclient import TestClient
from main import app, CAMERA_ACTIVE

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

def test_status():
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "state" in data
    assert "camera_active" in data
    assert "camera_status" in data

def test_durations(monkeypatch):
    # 🔧 Mock DB response para no depender de DB real
    monkeypatch.setattr("modules.storage.get_person_durations", lambda: {"p1": 10, "p2": 20})
    resp = client.get("/durations")
    assert resp.status_code == 200
    assert "p1" in resp.json()

def test_toggle_camera(monkeypatch):
    # 🔧 Mock notifications para que no falle si no está configurado
    monkeypatch.setattr("modules.notifications.notify", lambda x: None)

    resp = client.post("/toggle_camera")
    assert resp.status_code == 200
    data = resp.json()
    assert "camera_active" in data
    assert "camera_status" in data

    # 🔄 Volver a estado inicial
    client.post("/toggle_camera") 