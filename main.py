
# --- Standard Library Imports ---
import os
import cv2
import time
import queue
import threading
import logging
import numpy as np
from logging.handlers import TimedRotatingFileHandler
from datetime import timedelta

# --- FastAPI & Third Party Imports ---
from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Body, Form, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from ultralytics import YOLO

# --- Project Imports ---
from auth import create_access_token, get_current_user, authenticate_user, require_role, ACCESS_TOKEN_EXPIRE_MINUTES
from utils.camera_config import load_camera_url, save_camera_url
from modules import storage, notifications
from reports.daily_report import generate_daily_report
from reports.weekly_report import generate_weekly_report
from reports.monthly_report import generate_monthly_report

# --- Prometheus ---
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import prometheus_client

app = FastAPI()

# --- ENDPOINTS DE CONTROL DE CÁMARA ---
@app.api_route("/toggle_camera", methods=["GET", "POST"])
async def toggle_camera(
    request: Request,
    active: bool = Query(None),
    body: dict = Body(None)
):
    global CAMERA_ACTIVE, CAMERA_STATUS, capture_thread, frame_queue

    # Cargar la URL configurada de la cámara
    camera_url = load_camera_url()
    src = 0 if camera_url.strip() == "0" else camera_url.strip()

    # 1️⃣ Detectar si viene por GET (query param) o POST (body JSON/form)
    if request.method == "GET":
        if active is None:
            return {
                "success": False,
                "message": "Falta parámetro 'active' en query",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }
    else:  # POST
        if body and "active" in body:
            active = body["active"]
        else:
            return {
                "success": False,
                "message": "Falta 'active' en el body",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }

    # 2️⃣ Activar cámara
    if active:
        if not CAMERA_ACTIVE:
            test_cap = cv2.VideoCapture(src)
            time.sleep(1)
            if not test_cap.isOpened():
                CAMERA_STATUS = "OFFLINE"
                app.state.camera_status = CAMERA_STATUS
                return {
                    "success": False,
                    "message": "No se pudo activar la cámara.",
                    "status": CAMERA_STATUS,
                    "camera_url": camera_url
                }
            test_cap.release()
            capture_thread = CameraCapture(src, frame_queue, max_fps=15)
            capture_thread.start()
            CAMERA_ACTIVE = True
            CAMERA_STATUS = "ONLINE"
            app.state.camera_active = CAMERA_ACTIVE
            app.state.camera_status = CAMERA_STATUS
            return {
                "success": True,
                "message": "Cámara activada.",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }
        else:
            return {
                "success": True,
                "message": "La cámara ya está activa.",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }

    # 3️⃣ Desactivar cámara
    else:
        if CAMERA_ACTIVE and "capture_thread" in globals() and capture_thread is not None:
            capture_thread.stop()
            CAMERA_ACTIVE = False
            CAMERA_STATUS = "OFFLINE"
            app.state.camera_active = CAMERA_ACTIVE
            app.state.camera_status = CAMERA_STATUS
            return {
                "success": True,
                "message": "Cámara desactivada.",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }
        else:
            return {
                "success": True,
                "message": "La cámara ya está desactivada.",
                "status": CAMERA_STATUS,
                "camera_url": camera_url
            }
from fastapi import FastAPI, Depends, HTTPException, status
from auth import create_access_token, get_current_user

# NOTE: no usamos OAuth2PasswordRequestForm en la firma para /login,
# porque el frontend envía application/x-www-form-urlencoded sin grant_type.
from fastapi.security import OAuth2PasswordRequestForm

from ultralytics import YOLO


# --- Prometheus metrics initialization (safe for reload) ---
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import prometheus_client
def _init_prometheus_metrics():
    registry = prometheus_client.REGISTRY
    # Check if already registered
    metric_names = set(m.name for m in registry.collect())
    metrics = {}
    if "app_requests_total" not in metric_names:
        metrics["REQUEST_COUNT"] = Counter("app_requests_total", "Total de requests", ["method", "endpoint"])
    else:
        metrics["REQUEST_COUNT"] = prometheus_client.REGISTRY._names_to_collectors["app_requests_total"]
    if "app_request_latency_seconds" not in metric_names:
        metrics["REQUEST_LATENCY"] = Histogram("app_request_latency_seconds", "Latencia de requests", ["endpoint"])
    else:
        metrics["REQUEST_LATENCY"] = prometheus_client.REGISTRY._names_to_collectors["app_request_latency_seconds"]
    if "camera_capture_latency_seconds" not in metric_names:
        metrics["CAPTURE_LATENCY"] = Histogram("camera_capture_latency_seconds", "Latencia de captura de frames")
    else:
        metrics["CAPTURE_LATENCY"] = prometheus_client.REGISTRY._names_to_collectors["camera_capture_latency_seconds"]
    if "camera_inference_latency_seconds" not in metric_names:
        metrics["INFERENCE_LATENCY"] = Histogram("camera_inference_latency_seconds", "Latencia de inferencia YOLO")
    else:
        metrics["INFERENCE_LATENCY"] = prometheus_client.REGISTRY._names_to_collectors["camera_inference_latency_seconds"]
    if "camera_frames_processed_total" not in metric_names:
        metrics["FRAMES_PROCESSED"] = Counter("camera_frames_processed_total", "Frames procesados por postprocess")
    else:
        metrics["FRAMES_PROCESSED"] = prometheus_client.REGISTRY._names_to_collectors["camera_frames_processed_total"]
    return metrics

_metrics = _init_prometheus_metrics()
REQUEST_COUNT = _metrics["REQUEST_COUNT"]
REQUEST_LATENCY = _metrics["REQUEST_LATENCY"]
CAPTURE_LATENCY = _metrics["CAPTURE_LATENCY"]
INFERENCE_LATENCY = _metrics["INFERENCE_LATENCY"]
FRAMES_PROCESSED = _metrics["FRAMES_PROCESSED"]

# 🔐 Importamos helpers de auth.py (asegúrate que existan y funcionen)
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
 
 

# -----------------------------
# ENDPOINTS DE CONFIGURACIÓN DE CÁMARA (deben ir después de app, frame_queue, CameraCapture)
# -----------------------------

# Imports y endpoints movidos aquí, después de app y variables globales
from utils.camera_config import load_camera_url, save_camera_url
from fastapi.responses import PlainTextResponse
from fastapi import Form


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
# (tus templates están en dashboard/templates según tu estructura)
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


@app.get("/secure-data")
async def secure_data(user=Depends(get_current_user)):
    return {"data": f"Hola {user['username']} ({user['role']}), este es un endpoint protegido"} 


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            # Puedes agregar más variables de contexto aquí si tu dashboard las necesita
        },
    )

@app.post("/dashboard", response_class=HTMLResponse)
async def dashboard_post(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            # Puedes agregar más variables de contexto aquí si tu dashboard las necesita
        },
    )

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

# -----------------------------
# Inicialización segura en evento startup
# -----------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando storage.init_db()")
    storage.init_db()
    logger.info("storage.init_db() completado")
    # Inicializar estado en app.state para accesibilidad desde templates
    app.state.state = STATE
    app.state.camera_active = CAMERA_ACTIVE
    app.state.camera_status = CAMERA_STATUS
    logger.info("✅ Base de datos inicializada")

# -----------------------------
# Cierre seguro en evento shutdown
# -----------------------------
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
# 🔍 Cargar modelo YOLO
# -----------------------------
try:
    model = YOLO("yolov8n.pt")
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
                continue
            last_time = now

            if not self.queue.empty():
                try:
                    self.queue.get_nowait()
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

# --- ENDPOINTS DE CONFIGURACIÓN DE CÁMARA ---
from utils.camera_config import load_camera_url, save_camera_url
from fastapi.responses import PlainTextResponse
from fastapi import Form

# frame_queue debe ser global para que el endpoint pueda reiniciar la cámara
if 'frame_queue' not in globals():
    frame_queue = queue.Queue(maxsize=1)

@app.get("/camera_url", response_class=PlainTextResponse)
async def get_camera_url():
    return load_camera_url()

@app.post("/camera_url", response_class=PlainTextResponse)
async def set_camera_url(url: str = Form(...)):
    save_camera_url(url)
    # Reiniciar la cámara automáticamente
    global CAMERA_ACTIVE, CAMERA_STATUS, capture_thread, frame_queue
    try:
        if 'capture_thread' in globals() and capture_thread is not None:
            capture_thread.stop()
            time.sleep(0.2)
        camera_url = load_camera_url()
        src = 0 if camera_url.strip() == '0' else camera_url.strip()
        # Probar si la cámara se puede abrir antes de lanzar el hilo
        test_cap = cv2.VideoCapture(src)
        time.sleep(1)  # Espera breve para que OpenCV intente conectar
        if not test_cap.isOpened():
            CAMERA_ACTIVE = False
            CAMERA_STATUS = "OFFLINE"
            app.state.camera_active = CAMERA_ACTIVE
            app.state.camera_status = CAMERA_STATUS
            # Diagnóstico básico de errores RTSP/HTTP
            msg = "ERROR: No se pudo conectar a la cámara remota.\n\n"
            msg += "Sugerencias para depurar:\n"
            if not (src.startswith("rtsp://") or src.startswith("http://")):
                msg += "- La URL debe iniciar con 'rtsp://' o 'http://'. Verifica el formato.\n"
            msg += "- Verifica que la IP/dominio, usuario, contraseña y puerto sean correctos.\n"
            msg += "- Asegúrate de que la cámara esté encendida y accesible desde esta red.\n"
            msg += "- Si la cámara requiere usuario/contraseña, revisa que sean válidos.\n"
            msg += "- Prueba la URL en VLC, navegador o reproductor compatible para descartar problemas de red.\n"
            msg += "- Si la cámara está ocupada por otro software, ciérralo e inténtalo de nuevo.\n"
            msg += "\nEjemplo de URL RTSP: rtsp://usuario:contraseña@ip:puerto/stream\n"
            msg += "Ejemplo de URL HTTP: http://ip:puerto/ruta"
            return PlainTextResponse(msg, status_code=400)
        # Si se abrió, pero no se reciben frames, también es un error común
        ret, _ = test_cap.read()
        if not ret:
            test_cap.release()
            CAMERA_ACTIVE = False
            CAMERA_STATUS = "OFFLINE"
            app.state.camera_active = CAMERA_ACTIVE
            app.state.camera_status = CAMERA_STATUS
            msg = "ERROR: Se conectó a la cámara pero no se reciben imágenes.\n\n"
            msg += "Sugerencias:\n"
            msg += "- Verifica que el canal/stream de la cámara esté habilitado.\n"
            msg += "- Prueba la URL en VLC para ver si hay video.\n"
            msg += "- Revisa la configuración de la cámara (resolución, codec, etc).\n"
            return PlainTextResponse(msg, status_code=400)
        test_cap.release()
        capture_thread = CameraCapture(src, frame_queue, max_fps=15)
        capture_thread.start()
        CAMERA_ACTIVE = True
        CAMERA_STATUS = "ONLINE"
        app.state.camera_active = CAMERA_ACTIVE
        app.state.camera_status = CAMERA_STATUS
    except Exception as e:
        CAMERA_ACTIVE = False
        CAMERA_STATUS = "OFFLINE"
        app.state.camera_active = CAMERA_ACTIVE
        app.state.camera_status = CAMERA_STATUS
        msg = f"ERROR: {e}\n\nSugerencias:\n- Verifica el formato de la URL y la conectividad de red.\n- Consulta los logs del sistema para más detalles."
        return PlainTextResponse(msg, status_code=500)
    return "OK"

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from datetime import timedelta

@app.post("/login")
async def login(request: Request):
    """
    Acepta:
      - application/x-www-form-urlencoded (desde tu login.html con URLSearchParams)
      - application/json
    Devuelve JSON con access_token y también setea cookie (secure=False en dev).
    """
    # Leer credenciales
    username, password = None, None
    try:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        else:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Formato inválido")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username y password requeridos")

    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generar token con expiración
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "user")},
        expires_delta=access_token_expires,
    )

    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"username": user["username"], "role": user.get("role", "user")}
    })

    # Guardar token en cookie (en prod secure=True)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    return response

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/status")
async def get_status():
    # Cargar la URL configurada de la cámara
    camera_url = load_camera_url()
    return {
        "status": CAMERA_STATUS,
        "camera_url": camera_url
    }

@app.get("/reports/daily")
async def daily_report():
    path = generate_daily_report()
    return FileResponse(path, media_type="application/pdf", filename="daily_report.pdf")

@app.get("/reports/weekly")
async def weekly_report():
    path = generate_weekly_report()
    return FileResponse(path, media_type="application/pdf", filename="weekly_report.pdf")

@app.get("/reports/monthly")
async def monthly_report():
    path = generate_monthly_report()
    return FileResponse(path, media_type="application/pdf", filename="monthly_report.pdf")

@app.get("/durations")
async def get_durations():
    # Devuelve datos de ejemplo o tu lógica real
    return {"durations": []}