from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import cv2

from ultralytics import YOLO

from modules import storage, alerts, notifications

app = FastAPI()

# Inicializar base de datos
storage.init_db()

# Estado en memoria
STATE = {
    "inside": 0,
    "entered": 0,
    "exited": 0,
}

# Control de cámara
CAMERA_ACTIVE = False

# Configurar templates y archivos estáticos
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# ---------------------------
# Cargar modelo YOLOv8
# ---------------------------
model = YOLO("yolov8n.pt")  # modelo liviano de detección

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Renderiza la interfaz gráfica"""
    return templates.TemplateResponse(
        "index.html", {"request": request, "state": STATE, "camera_active": CAMERA_ACTIVE}
    )

@app.get("/status")
async def get_status():
    return STATE

@app.post("/event/{action}")
async def register_event(action: str):
    if action not in ["entered", "exited"]:
        return {"error": "Acción no válida"}

    if action == "entered":
        STATE["entered"] += 1
        STATE["inside"] += 1
    else:
        STATE["exited"] += 1
        STATE["inside"] = max(0, STATE["inside"] - 1)

    storage.save_event(action)

    alert_msg = alerts.check_capacity(STATE["inside"])
    if alert_msg:
        notifications.send_email("Alerta de aforo", alert_msg)

    return {"status": "ok", "state": STATE}

# -------------------------
# 📷 Video con YOLOv8
# -------------------------
def generate_video():
    global CAMERA_ACTIVE
    cap = cv2.VideoCapture(0)

    while CAMERA_ACTIVE:
        success, frame = cap.read()
        if not success:
            break

        # Hacer detección con YOLOv8
        results = model(frame, stream=True)

        count_persons = 0
        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                if model.names[cls] == "person":  # Solo contamos personas
                    count_persons += 1
                    # Dibujar bounding box
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, "Person", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Actualizar estado global
        STATE["inside"] = count_persons

        # Codificar y enviar frame
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

    cap.release()

@app.get("/video")
async def video_feed():
    if not CAMERA_ACTIVE:
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(generate_video(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/toggle_camera")
async def toggle_camera():
    global CAMERA_ACTIVE
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    return {"camera_active": CAMERA_ACTIVE}