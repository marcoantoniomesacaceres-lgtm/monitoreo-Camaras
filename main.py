import os
import cv2
import time
import logging
import numpy as np
from logging.handlers import TimedRotatingFileHandler
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from modules import storage, notifications
from reports.daily_report import generate_daily_report
from reports.weekly_report import generate_weekly_report
from reports.monthly_report import generate_monthly_report

# -----------------------------
# 📜 Configuración de logs
# -----------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1, backupCount=7, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.info("🚀 Aplicación iniciada")

# -----------------------------
# 🚀 FastAPI App
# -----------------------------
app = FastAPI()
storage.init_db()
logger.info("✅ Base de datos inicializada")

# -----------------------------
# 🌐 Estado Global
# -----------------------------
STATE = {"inside": 0, "entered": 0, "exited": 0}
CAMERA_ACTIVE = False
CAMERA_STATUS = "OFFLINE"

STATUS_TRANSLATIONS = {
    "ONLINE": "En línea",
    "OFFLINE": "Fuera de línea",
    "RECONNECTING": "Reconectando",
}

templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# -----------------------------
# 🔍 Cargar modelo YOLO
# -----------------------------
try:
    model = YOLO("yolov8n.pt")
    logger.info("✅ Modelo YOLO cargado exitosamente")
except Exception as e:
    model = None
    logger.error(f"❌ Error cargando modelo YOLO: {e}", exc_info=True)

# Historial para debounce de eventos
last_positions = {}
last_events = {}
EVENT_DEBOUNCE_SECONDS = 3

# -----------------------------
# ♻️ Circuit Breakers
# -----------------------------
class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_time=30, name="GENERIC"):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure = 0
        self.open = False
        self.name = name

    def call(self, func, *args, **kwargs):
        if self.open:
            if time.time() - self.last_failure > self.recovery_time:
                logger.info(f"♻️ Circuit breaker {self.name} HALF-OPEN, probando de nuevo...")
                self.open = False
                self.failures = 0
            else:
                raise RuntimeError(f"🚫 Circuit breaker {self.name} abierto")

        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.failures += 1
            self.last_failure = time.time()
            if self.failures >= self.failure_threshold:
                self.open = True
                logger.error(f"❌ Circuit breaker {self.name} activado")
            raise e

db_breaker = CircuitBreaker(name="DB")
camera_breaker = CircuitBreaker(failure_threshold=5, recovery_time=15, name="CAMERA")

# -----------------------------
# 🩺 Health & Readiness
# -----------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/readiness")
async def readiness():
    try:
        db_breaker.call(storage.get_stats)
        if model is None:
            raise RuntimeError("YOLO no cargado")
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"❌ Readiness fail: {e}")
        return JSONResponse(status_code=500, content={"status": "not ready", "error": str(e)})

# -----------------------------
# 📊 Métricas Prometheus
# -----------------------------
REQUEST_COUNT = Counter("app_requests_total", "Total de requests", ["method", "endpoint"])
REQUEST_LATENCY = Histogram("app_request_latency_seconds", "Latencia de requests", ["endpoint"])

@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    latency = time.time() - start
    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(latency)
    return response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# -----------------------------
# 📄 Páginas principales
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "state": STATE,
        "camera_active": CAMERA_ACTIVE,
        "camera_status": STATUS_TRANSLATIONS.get(CAMERA_STATUS.split()[0], CAMERA_STATUS),
    })

@app.get("/status")
async def get_status():
    return {"state": STATE, "camera_active": CAMERA_ACTIVE,
            "camera_status": STATUS_TRANSLATIONS.get(CAMERA_STATUS.split()[0], CAMERA_STATUS)}

@app.get("/durations")
async def get_durations():
    return db_breaker.call(storage.get_person_durations)

# -----------------------------
# 📑 Reportes
# -----------------------------
@app.get("/reports/daily")
async def daily_report():
    return FileResponse(generate_daily_report(), media_type="application/pdf", filename="daily_report.pdf")

@app.get("/reports/weekly")
async def weekly_report():
    return FileResponse(generate_weekly_report(), media_type="application/pdf", filename="weekly_report.pdf")

@app.get("/reports/monthly")
async def monthly_report():
    return FileResponse(generate_monthly_report(), media_type="application/pdf", filename="monthly_report.pdf")

# -----------------------------
# 📷 Cámara con YOLO + retries + debounce + circuit breaker
# -----------------------------
def make_offline_frame(width=640, height=480, text="CÁMARA FUERA DE LÍNEA"):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, text, (50, height // 2), font, 1, (0,0,255), 2, cv2.LINE_AA)
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()

def notify_camera_status(status, details=None):
    try:
        if hasattr(notifications, "notify"):
            notifications.notify({"camera_status": status, "details": details})
        elif hasattr(notifications, "send"):
            notifications.send({"camera_status": status, "details": details})
    except Exception:
        logger.debug("No se pudo enviar notificación de cámara")

def generate_video():
    global CAMERA_ACTIVE, CAMERA_STATUS, last_positions, last_events
    offline_frame = make_offline_frame()

    while CAMERA_ACTIVE:
        try:
            cap = camera_breaker.call(cv2.VideoCapture, 0)
        except Exception as e:
            CAMERA_STATUS = "OFFLINE"
            logger.warning(f"⚠️ Cámara no disponible ({e}), retry...")
            notify_camera_status("OFFLINE", str(e))
            time.sleep(2)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + offline_frame + b"\r\n"
            continue

        if not cap.isOpened():
            CAMERA_STATUS = "OFFLINE"
            logger.warning("⚠️ Cámara no se pudo abrir")
            time.sleep(2)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + offline_frame + b"\r\n"
            continue

        CAMERA_STATUS = "ONLINE"
        notify_camera_status("ONLINE")
        while CAMERA_ACTIVE:
            success, frame = cap.read()
            if not success:
                logger.warning("⚠️ Error de frame")
                notify_camera_status("OFFLINE", "Fallo frame")
                break

            try:
                results = model.track(frame, persist=True, stream=True)
            except Exception as e:
                logger.error(f"❌ Error YOLO: {e}", exc_info=True)
                _, buf = cv2.imencode(".jpg", frame)
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
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
                        action = "entered" if prev_y > frame.shape[0]//2 and cy <= frame.shape[0]//2 else \
                                 "exited" if prev_y < frame.shape[0]//2 and cy >= frame.shape[0]//2 else None

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
                                logger.info(f"👤 Persona {person_id} {action}")
                                last_events[person_id] = {"action": action, "time": now}

                    last_positions[person_id] = cy

            cv2.line(frame, (0, frame.shape[0]//2), (frame.shape[1], frame.shape[0]//2), (255, 0, 0), 2)
            _, buf = cv2.imencode(".jpg", frame)
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"

        cap.release()

    CAMERA_STATUS = "OFFLINE"
    notify_camera_status("OFFLINE", "Stream terminado")

@app.get("/video")
async def video_feed():
    if not CAMERA_ACTIVE:
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(generate_video(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/toggle_camera")
async def toggle_camera():
    global CAMERA_ACTIVE, CAMERA_STATUS
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    CAMERA_STATUS = "ONLINE" if CAMERA_ACTIVE else "OFFLINE"
    notify_camera_status(CAMERA_STATUS)
    return {"camera_active": CAMERA_ACTIVE, "camera_status": STATUS_TRANSLATIONS.get(CAMERA_STATUS.split()[0], CAMERA_STATUS)}