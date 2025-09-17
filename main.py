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
import time  # 👈 Necesario para debounce

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
CAMERA_ACTIVE = False

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

# Historial de posiciones por ID
last_positions = {}

# Historial de últimos eventos (para debounce)
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
        {"request": request, "state": STATE, "camera_active": CAMERA_ACTIVE},
    )

@app.get("/status")
async def get_status():
    logger.debug(f"📊 Estado solicitado: {STATE}")
    return STATE

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
# 📷 Video con YOLOv8 + Tracking
# -----------------------------
def generate_video():
    global CAMERA_ACTIVE, last_positions, last_events

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("❌ No se pudo abrir la cámara")
        return

    line_y = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) // 2)
    logger.info("📷 Cámara iniciada para streaming")

    while CAMERA_ACTIVE:
        success, frame = cap.read()
        if not success:
            logger.error("⚠️ Fallo al leer frame de la cámara")
            break

        try:
            results = model.track(frame, persist=True, stream=True)
        except Exception as e:
            logger.error(f"❌ Error en inferencia YOLO: {e}", exc_info=True)
            continue

        for r in results:
            if r.boxes.id is None:
                continue
            for box in r.boxes:
                cls = int(box.cls[0])
                if model.names[cls] != "person":
                    continue

                person_id = int(box.id[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                # Lógica de cruce con filtro de debounce
                if person_id in last_positions:
                    prev_y = last_positions[person_id]
                    action = None

                    if prev_y > line_y and cy <= line_y:  # entrada
                        action = "entered"
                    elif prev_y < line_y and cy >= line_y:  # salida
                        action = "exited"

                    if action:
                        now = time.time()
                        last_event = last_events.get(person_id)

                        # Verificar debounce
                        if not last_event or last_event["action"] != action or (now - last_event["time"]) > EVENT_DEBOUNCE_SECONDS:
                            if action == "entered":
                                STATE["entered"] += 1
                                STATE["inside"] += 1
                            else:
                                STATE["exited"] += 1
                                STATE["inside"] = max(0, STATE["inside"] - 1)

                            storage.save_event(action, person_id)
                            logger.info(f"👤 Persona {person_id} { 'entró' if action == 'entered' else 'salió' }")

                            # Actualizar último evento
                            last_events[person_id] = {"action": action, "time": now}

                last_positions[person_id] = cy

        # Dibujar línea virtual
        cv2.line(frame, (0, line_y), (frame.shape[1], line_y), (255, 0, 0), 2)

        _, buffer = cv2.imencode(".jpg", frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )

    cap.release()
    logger.info("📷 Cámara detenida")

@app.get("/video")
async def video_feed():
    if not CAMERA_ACTIVE:
        logger.warning("⚠️ Solicitud de video pero la cámara está apagada")
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(
        generate_video(), media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/toggle_camera")
async def toggle_camera():
    global CAMERA_ACTIVE
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    if CAMERA_ACTIVE:
        logger.info("✅ Cámara encendida")
    else:
        logger.info("🛑 Cámara apagada")
    return {"camera_active": CAMERA_ACTIVE} 