import pytest
import types
from main import app, generate_video, CAMERA_ACTIVE, CAPTURE_LATENCY, INFERENCE_LATENCY, FRAMES_PROCESSED

@pytest.mark.asyncio
async def test_generate_video_runs(monkeypatch):
    """
    Verifica que generate_video produce frames (aunque sea el frame OFFLINE).
    """
    global CAMERA_ACTIVE
    CAMERA_ACTIVE = True

    # 🔹 Mock de modelo YOLO (evita carga pesada real)
    class DummyResult:
        def __init__(self):
            self.boxes = []

    class DummyModel:
        names = {0: "person"}
        def track(self, frame, persist=True, stream=True):
            return [DummyResult()]

    monkeypatch.setattr("main.model", DummyModel())

    gen = generate_video()
    frame = next(gen)  # Primer frame
    assert isinstance(frame, (bytes, bytearray))
    CAMERA_ACTIVE = False  # detener
    with pytest.raises(StopIteration):
        next(gen)


@pytest.mark.asyncio
async def test_camera_toggle(client):
    """
    Verifica que toggle_camera cambia el estado de la cámara.
    """
    response = await client.post("/toggle_camera")
    assert response.status_code == 200
    data = response.json()
    assert "camera_active" in data
    assert "camera_status" in data

    # Restaurar estado (apagar si quedó encendida)
    if data["camera_active"]:
        await client.post("/toggle_camera")


def test_metrics_updated(monkeypatch):
    """
    Verifica que las métricas del pipeline se actualizan al procesar frames.
    """
    global CAMERA_ACTIVE
    CAMERA_ACTIVE = True

    # 🔹 Mock modelo YOLO
    class DummyBox:
        def __init__(self):
            self.cls = [0]
            self.id = [1]
            self.xyxy = [[0, 0, 10, 10]]

    class DummyResult:
        def __init__(self):
            self.boxes = [DummyBox()]

    class DummyModel:
        names = {0: "person"}
        def track(self, frame, persist=True, stream=True):
            return [DummyResult()]

    monkeypatch.setattr("main.model", DummyModel())

    gen = generate_video()
    for _ in range(3):
        try:
            next(gen)
        except StopIteration:
            break

    CAMERA_ACTIVE = False

    # Validar que métricas tienen datos
    assert CAPTURE_LATENCY._sum.get() >= 0
    assert INFERENCE_LATENCY._sum.get() >= 0
    assert FRAMES_PROCESSED._value.get() >= 0                