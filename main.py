from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import os
import cv2
import logging
from logging.handlers import TimedRotatingFileHandler
from ultralytics import YOLO
from modules import storage, alerts, notifications
from reports.daily_report import generate_daily_report
from reports.weekly_report import generate_weekly_report
from reports.monthly_report import generate_monthly_report
import time
import numpy as np

# -----------------------------
# 📜 Configuración de logs
# -----------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
handler.setFormatter(logging.Formatter(log_format))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# -----------------------------
# 🚀 FastAPI App
# -----------------------------
app = FastAPI()
storage.init_db()
logger.info("🚀 Aplicación iniciada y base de datos inicializada")

# Estado global
STATE = {"inside": 0, "entered": 0, "exited": 0}
CAMERA_ACTIVE = False  # control desde UI
CAMERA_STATUS = "OFFLINE"  # "ONLINE", "OFFLINE", "RECONNECTING"

# Configuración de templates
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# ⚡ Endpoint para favicon
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join("dashboard", "static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    logger.warning("⚠️ Favicon solicitado pero no encontrado")
    return JSONResponse(status_code=404, content={"error": "favicon not found"})

# -----------------------------
# 🔍 Cargar modelo YOLOv8
# -----------------------------
try:
    model = YOLO("yolov8n.pt")
    logger.info("✅ Modelo YOLO cargado exitosamente")
except Exception as e:
    logger.error(f"❌ Error cargando modelo YOLO: {e}", exc_info=True)
    raise

# Historial de posiciones y eventos
last_positions = {}
last_events = {}  # {person_id: {"action": "entered"/"exited", "time": timestamp}}
EVENT_DEBOUNCE_SECONDS = 3  # Tiempo mínimo entre eventos repetidos

# -----------------------------
# 📄 Páginas principales
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    logger.info("📄 Página principal servida")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "state": STATE,
            "camera_active": CAMERA_ACTIVE,
            "camera_status": CAMERA_STATUS,
        },
    )

@app.get("/status")
async def get_status():
    logger.debug(f"📊 Estado solicitado: {STATE} - CAMERA_STATUS: {CAMERA_STATUS}")
    return {"state": STATE, "camera_active": CAMERA_ACTIVE, "camera_status": CAMERA_STATUS}

@app.get("/durations")
async def get_durations():
    logger.info("⏱️ Consulta de tiempos de permanencia")
    return storage.get_person_durations()

# -----------------------------
# 📑 Reportes (PDF)
# -----------------------------
@app.get("/reports/daily")
async def daily_report():
    filepath = generate_daily_report()
    logger.info("📑 Reporte diario generado")
    return FileResponse(filepath, media_type="application/pdf", filename="daily_report.pdf")

@app.get("/reports/weekly")
async def weekly_report():
    filepath = generate_weekly_report()
    logger.info("📑 Reporte semanal generado")
    return FileResponse(filepath, media_type="application/pdf", filename="weekly_report.pdf")

@app.get("/reports/monthly")
async def monthly_report():
    filepath = generate_monthly_report()
    logger.info("📑 Reporte mensual generado")
    return FileResponse(filepath, media_type="application/pdf", filename="monthly_report.pdf")

# -----------------------------
# 🔧 Utilidades para reconexión
# -----------------------------
def make_offline_frame(width=640, height=480, text="CAMERA OFFLINE"):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thickness = 1.0, 2
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    x, y = (width - text_size[0]) // 2, (height + text_size[1]) // 2
    cv2.putText(frame, text, (x, y), font, scale, (0, 0, 255), thickness, cv2.LINE_AA)
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()

def notify_camera_status(status, details=None):
    try:
        if hasattr(notifications, "notify"):
            notifications.notify({"camera_status": status, "details": details})
        elif hasattr(notifications, "send"):
            notifications.send({"camera_status": status, "details": details})
    except Exception:
        logger.debug("No se pudo enviar notificación de cámara.")

# -----------------------------
# 📷 Video con YOLOv8 + Tracking + Reconexión + Debounce
# -----------------------------
def generate_video():
    global CAMERA_ACTIVE, CAMERA_STATUS, last_positions, last_events

    BASE_BACKOFF, MAX_BACKOFF, MAX_ATTEMPTS = 1.0, 16.0, None
    offline_frame = make_offline_frame()

    while CAMERA_ACTIVE:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            CAMERA_STATUS = "OFFLINE"
            logger.warning("⚠️ No se pudo abrir la cámara: entrando en reconexión")
            notify_camera_status("OFFLINE", "No se pudo abrir cámara")
            attempt, backoff = 0, BASE_BACKOFF

            while CAMERA_ACTIVE and (MAX_ATTEMPTS is None or attempt < MAX_ATTEMPTS):
                attempt += 1
                CAMERA_STATUS = f"RECONNECTING (attempt {attempt})"
                logger.info(f"🔄 Intento reconexión #{attempt} en {backoff:.1f}s")
                notify_camera_status("RECONNECTING", {"attempt": attempt})

                start_wait = time.time()
                while time.time() - start_wait < backoff and CAMERA_ACTIVE:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + offline_frame + b"\r\n"
                    time.sleep(1.0)

                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    CAMERA_STATUS = "ONLINE"
                    logger.info("✅ Cámara reconectada")
                    notify_camera_status("ONLINE")
                    break
                backoff = min(backoff * 2.0, MAX_BACKOFF)

            if not cap or not cap.isOpened():
                CAMERA_STATUS = "OFFLINE"
                logger.error("❌ No fue posible reconectar la cámara")
                notify_camera_status("OFFLINE", "Reconexión fallida")
                while CAMERA_ACTIVE:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + offline_frame + b"\r\n"
                    time.sleep(1.0)
                break

        line_y = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) // 2) or 240
        CAMERA_STATUS = "ONLINE"
        logger.info("📷 Cámara iniciada para streaming")
        notify_camera_status("ONLINE")

        while CAMERA_ACTIVE:
            success, frame = cap.read()
            if not success:
                logger.warning("⚠️ Fallo al leer frame. Intentando reconectar...")
                cap.release()
                CAMERA_STATUS = "OFFLINE"
                notify_camera_status("OFFLINE", "Fallo lectura frame")
                break

            try:
                results = model.track(frame, persist=True, stream=True)
            except Exception as e:
                logger.error(f"❌ Error YOLO: {e}", exc_info=True)
                _, buffer = cv2.imencode(".jpg", frame)
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
                continue

            for r in results:
                if not hasattr(r, "boxes") or r.boxes is None:
                    continue
                for box in r.boxes:
                    if not hasattr(box, "id") or box.id is None:
                        continue
                    cls = int(box.cls[0])
                    if model.names[cls] != "person":
                        continue

                    person_id = int(box.id[0])
                    _, y1, _, y2 = map(int, box.xyxy[0])
                    cy = (y1 + y2) // 2

                    if person_id in last_positions:
                        prev_y = last_positions[person_id]
                        action = "entered" if prev_y > line_y and cy <= line_y else \
                                 "exited" if prev_y < line_y and cy >= line_y else None

                        if action:
                            now = time.time()
                            last_event = last_events.get(person_id)
                            if not last_event or last_event["action"] != action or (now - last_event["time"]) > EVENT_DEBOUNCE_SECONDS:
                                if action == "entered":
                                    STATE["entered"] += 1
                                    STATE["inside"] += 1
                                else:
                                    STATE["exited"] += 1
                                    STATE["inside"] = max(0, STATE["inside"] - 1)

                                storage.save_event(action, person_id)
                                logger.info(f"👤 Persona {person_id} { 'entró' if action == 'entered' else 'salió' }")
                                last_events[person_id] = {"action": action, "time": now}

                    last_positions[person_id] = cy

            cv2.line(frame, (0, line_y), (frame.shape[1], line_y), (255, 0, 0), 2)
            _, buffer = cv2.imencode(".jpg", frame)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"

        cap.release()

    CAMERA_STATUS = "OFFLINE"
    logger.info("📷 Cámara detenida")
    notify_camera_status("OFFLINE", "Stream terminado")

@app.get("/video")
async def video_feed():
    if not CAMERA_ACTIVE:
        logger.warning("⚠️ Solicitud de video pero cámara apagada")
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(
        generate_video(), media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/toggle_camera")
async def toggle_camera():
    global CAMERA_ACTIVE, CAMERA_STATUS
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    if CAMERA_ACTIVE:
        CAMERA_STATUS = "ONLINE"
        logger.info("✅ Cámara encendida")
        notify_camera_status("ONLINE")
    else:
        CAMERA_STATUS = "OFFLINE"
        logger.info("🛑 Cámara apagada")
        notify_camera_status("OFFLINE")
    return {"camera_active": CAMERA_ACTIVE, "camera_status": CAMERA_STATUS} 