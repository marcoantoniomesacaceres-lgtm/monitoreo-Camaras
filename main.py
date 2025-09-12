from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import cv2

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

# Configurar templates y archivos estáticos
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Renderiza la interfaz gráfica"""
    return templates.TemplateResponse("index.html", {"request": request, "state": STATE})


@app.get("/status")
async def get_status():
    """Devuelve estado actual en JSON"""
    return STATE


@app.post("/event/{action}")
async def register_event(action: str):
    """Registra manualmente entrada/salida"""
    if action not in ["entered", "exited"]:
        return {"error": "Acción no válida"}

    if action == "entered":
        STATE["entered"] += 1
        STATE["inside"] += 1
    else:
        STATE["exited"] += 1
        STATE["inside"] = max(0, STATE["inside"] - 1)

    storage.save_event(action)

    # Checar alertas
    alert_msg = alerts.check_capacity(STATE["inside"])
    if alert_msg:
        notifications.send_email("Alerta de aforo", alert_msg)

    return {"status": "ok", "state": STATE}


# -------------------------
# 📷 Video en tiempo real
# -------------------------
def generate_video():
    cap = cv2.VideoCapture(0)  # 0 = cámara web local
    while True:
        success, frame = cap.read()
        if not success:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.get("/video")
async def video_feed():
    """Stream de la cámara en vivo"""
    return StreamingResponse(generate_video(), media_type="multipart/x-mixed-replace; boundary=frame")