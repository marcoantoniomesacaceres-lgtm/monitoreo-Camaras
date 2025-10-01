
# --- Standard Library Imports ---
import os
import logging
from logging.handlers import TimedRotatingFileHandler

# --- Third Party Imports ---
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import prometheus_client

# --- Project Module Imports ---
from modules import storage
import state
from routers import auth as auth_router, camera as camera_router, data as data_router, reports as reports_router

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
# 🚀 FastAPI App & Global State
# -----------------------------
app = FastAPI()

# Configuración de plantillas y archivos estáticos
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# -----------------------------
# 📊 Prometheus Metrics
# -----------------------------
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

# -----------------------------
# Inicialización segura en evento startup
# -----------------------------
@app.on_event("startup")
async def startup_event():
    logger.info("Iniciando storage.init_db()")
    storage.init_db()
    logger.info("storage.init_db() completado")
    # Inicializar estado en app.state para accesibilidad desde templates
    app.state.state = state.STATE
    app.state.camera_active = state.CAMERA_ACTIVE
    app.state.camera_status = state.CAMERA_STATUS
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

# --- Incluir Routers ---
app.include_router(auth_router.router)
app.include_router(camera_router.router)
app.include_router(data_router.router)
app.include_router(reports_router.router)