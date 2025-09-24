import os
import cv2
import time
import queue
import threading
import logging
import jwt
import numpy as np
from logging.handlers import TimedRotatingFileHandler
from datetime import timedelta

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm

from ultralytics import YOLO
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# 🔐 Importamos helpers de auth.py
from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_role,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# 📦 Módulos propios
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

handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
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

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# Inicialización segura en evento startup
@app.on_event("startup")
async def startup_event():
    storage.init_db()
    logger.info("✅ Base de datos inicializada")

# Cierre seguro en evento shutdown
@app.on_event("shutdown")
async def shutdown_event():
    try:
        if hasattr(storage, "close_db"):
            storage.close_db()
            logger.info("🛑 Conexión a base de datos cerrada correctamente")
        else:
            logger.warning("⚠️ storage.close_db() no está implementado")
    except Exception as e:
        logger.error(f"❌ Error cerrando la base de datos: {e}")

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
    model = YOLO("yolov8n.pt")   # 👈 modelo ligero por rendimiento
    logger.info("✅ Modelo YOLO cargado exitosamente")
except Exception as e:
    model = None
    logger.error(f"❌ Error cargando modelo YOLO: {e}", exc_info=True)

# Historial para debounce de eventos
last_positions, last_events = {}, {}
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
# 📷 Clase cámara optimizada
# -----------------------------
class CameraCapture(threading.Thread):
    def __init__(self, src, frame_queue, max_fps=15):
        super().__init__(daemon=True)
        self.src = src
        self.cap = cv2.VideoCapture(src)
        self.queue = frame_queue
        self.running = True
        self.max_fps = max_fps
        self.frame_time = 1.0 / max_fps

    def run(self):
        logger.info("🎥 Captura iniciada")
        last_time = 0
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            now = time.time()
            if now - last_time < self.frame_time:
                continue  # limitamos FPS
            last_time = now

            if not self.queue.empty():
                try:
                    self.queue.get_nowait()  # 👈 descartamos frame viejo
                except queue.Empty:
                    pass

            try:
                self.queue.put_nowait(frame)
            except queue.Full:
                pass

        self.cap.release()
        logger.info("🎥 Captura detenida")

    def stop(self):
        self.running = False

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
REQUEST_COUNT = Counter(
    "app_requests_total", "Total de requests", ["method", "endpoint"]
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds", "Latencia de requests", ["endpoint"]
)
CAPTURE_LATENCY = Histogram(
    "camera_capture_latency_seconds", "Latencia de captura de frames"
)
INFERENCE_LATENCY = Histogram(
    "camera_inference_latency_seconds", "Latencia de inferencia YOLO"
)
FRAMES_PROCESSED = Counter(
    "camera_frames_processed_total", "Frames procesados por postprocess"
)


@app.middleware("http")
async def add_metrics(request: Request, call_next):
    """
    Middleware que mide cuántas requests llegan y cuánto tardan.
    """
    start = time.time()
    response = await call_next(request)
    latency = time.time() - start

    REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(latency)

    return response


@app.get("/metrics")
async def metrics():
    """
    Endpoint para que Prometheus scrapee métricas.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST) 

# -----------------------------
# 📄 Páginas principales
# -----------------------------
# 📌 Ruta inicial (redirige según login)
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user=Depends(get_current_user)):
    """
    Si el usuario está autenticado, carga index.html.
    Si no, carga login.html.
    """
    if not user:  # token inválido o ausente
        return templates.TemplateResponse("login.html", {"request": request})

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "state": app.state.state,
            "camera_active": app.state.camera_active,
            "camera_status": STATUS_TRANSLATIONS.get(
                getattr(app.state, "camera_status", "Desconocido").split()[0],
                getattr(app.state, "camera_status", "Desconocido"),
            ),
            "user": user,
        },
    )


@app.get("/status")
async def get_status(user: dict = Depends(get_current_user)):
    return {
        "status": "ok",
        "user": user["username"],
        "role": user["role"],
        "state": STATE,
        "camera_active": CAMERA_ACTIVE,
        "camera_status": STATUS_TRANSLATIONS.get(
            CAMERA_STATUS.split()[0],
            CAMERA_STATUS
        ),
    }


@app.get("/durations")
async def get_durations(user=Depends(require_role("operator"))):
    return db_breaker.call(storage.get_person_durations)

# -----------------------------
# 📑 Reportes
# -----------------------------
@app.get("/reports/daily")
async def daily_report(user=Depends(require_role("admin"))):
    return FileResponse(generate_daily_report(), media_type="application/pdf", filename="daily_report.pdf")


@app.get("/reports/weekly")
async def weekly_report(user=Depends(require_role("admin"))):
    return FileResponse(generate_weekly_report(), media_type="application/pdf", filename="weekly_report.pdf")


@app.get("/reports/monthly")
async def monthly_report(user=Depends(require_role("admin"))):
    return FileResponse(generate_monthly_report(), media_type="application/pdf", filename="monthly_report.pdf")

# -----------------------------
# 📷 Cámara con pipeline
# -----------------------------
def make_offline_frame(width=640, height=480, text="Camara cargando...."):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, text, (50, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1, (128, 0, 8), 2, cv2.LINE_AA)
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


def generate_video(resize_to=(480, 360), frame_skip=2, result_queue_size=5, output_queue_size=2):
    global CAMERA_ACTIVE, CAMERA_STATUS, last_positions, last_events

    frame_queue = queue.Queue(maxsize=1)   # 👈 solo guardamos el último frame
    result_queue = queue.Queue(maxsize=1)
    output_queue = queue.Queue(maxsize=1)
    stop_event = threading.Event()
    offline_frame = make_offline_frame(width=resize_to[0], height=resize_to[1])

    last_valid_frame = offline_frame

    def put_latest(q: queue.Queue, item):
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
        try:
            q.put_nowait(item)
        except queue.Full:
            pass

    # 🚀 Hilo A: captura
    camera_thread = CameraCapture(0, frame_queue)
    camera_thread.start()

    # 🚀 Hilo B: inferencia
    def inference_thread():
        if model is None:
            logger.error("❌ Modelo YOLO no cargado")
            return
        logger.info("🔬 Inference iniciado")
        while CAMERA_ACTIVE and not stop_event.is_set():
            try:
                frame = frame_queue.get(timeout=2)
            except queue.Empty:
                continue

            frame = cv2.resize(frame, resize_to)

            start = time.time()
            try:
                results = list(model.track(frame, persist=True, stream=True))
            except Exception as e:
                logger.error(f"❌ Error YOLO: {e}", exc_info=True)
                results = []
            INFERENCE_LATENCY.observe(time.time() - start)

            put_latest(result_queue, (frame, results))
        logger.info("🔬 Inference finalizado")

    # 🚀 Hilo C: postprocess + DB
    def postprocess_thread():
        logger.info("🧩 Postprocess iniciado")
        while CAMERA_ACTIVE and not stop_event.is_set():
            try:
                frame, results = result_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                h_half = frame.shape[0] // 2
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
                            action = (
                                "entered"
                                if prev_y > h_half and cy <= h_half
                                else "exited"
                                if prev_y < h_half and cy >= h_half
                                else None
                            )
                            if action:
                                now = time.time()
                                last_event = last_events.get(person_id)
                                if not last_event or last_event["action"] != action or (
                                    now - last_event["time"]
                                ) > EVENT_DEBOUNCE_SECONDS:
                                    if action == "entered":
                                        STATE["entered"] += 1
                                        STATE["inside"] += 1
                                    else:
                                        STATE["exited"] += 1
                                        STATE["inside"] = max(0, STATE["inside"] - 1)
                                    try:
                                        db_breaker.call(storage.save_event, action, person_id)
                                    except Exception as e:
                                        logger.error(f"❌ Error DB: {e}")
                                    logger.info(f"👤 Persona {person_id} {action}")
                                    last_events[person_id] = {"action": action, "time": now}

                        last_positions[person_id] = cy

                cv2.line(frame, (0, h_half), (frame.shape[1], h_half), (255, 0, 0), 2)
                _, buf = cv2.imencode(".jpg", frame)
                put_latest(output_queue, buf.tobytes())
                FRAMES_PROCESSED.inc()
            except Exception as e:
                logger.error(f"❌ Postprocess error: {e}", exc_info=True)
        logger.info("🧩 Postprocess finalizado")

    # Lanzar hilos
    threads = [
        threading.Thread(target=inference_thread, daemon=True),
        threading.Thread(target=postprocess_thread, daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while CAMERA_ACTIVE:
            try:
                jpeg = output_queue.get(timeout=0.5)
                last_valid_frame = jpeg
            except queue.Empty:
                jpeg = last_valid_frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
    finally:
        stop_event.set()
        camera_thread.stop()
        time.sleep(0.2)
        logger.info("🛑 Pipeline detenido")

# -----------------------------
# 📡 Endpoints cámara
# -----------------------------
@app.get("/video")
async def video_feed(user=Depends(get_current_user)):
    if not CAMERA_ACTIVE:
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(generate_video(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/toggle_camera")
async def toggle_camera(user=Depends(require_role("admin"))):
    global CAMERA_ACTIVE, CAMERA_STATUS
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    CAMERA_STATUS = "ONLINE" if CAMERA_ACTIVE else "OFFLINE"
    notify_camera_status(CAMERA_STATUS)
    return {
        "camera_active": CAMERA_ACTIVE,
        "camera_status": STATUS_TRANSLATIONS.get(CAMERA_STATUS.split()[0], CAMERA_STATUS),
    }

# -----------------------------
# 🔐 Login con JWT
# -----------------------------
@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]},
        expires_delta=access_token_expires,
    )

    # Creamos la respuesta en JSON
    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "role": user["role"],
        },
    })

    # Guardamos el token también en una cookie segura
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,       # ❌ JS no puede leer la cookie → más seguro
        secure=True,         # ✅ solo sobre HTTPS (útil en prod)
        samesite="Lax",      # evita CSRF básicos
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return response