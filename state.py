import queue
from ultralytics import YOLO
import logging

logger = logging.getLogger(__name__)

# Estado Global de la Aplicación

# Estado del contador
STATE = {"inside": 0, "entered": 0, "exited": 0}

# Estado de la cámara
CAMERA_ACTIVE = False
CAMERA_STATUS = "OFFLINE"
frame_queue = queue.Queue(maxsize=1)
capture_thread = None

# Modelo YOLO
try:
    model = YOLO("yolov8n.pt")
    logger.info("✅ Modelo YOLO cargado exitosamente desde state.py")
except Exception as e:
    model = None
    logger.error(f"❌ Error cargando modelo YOLO: {e}", exc_info=True)