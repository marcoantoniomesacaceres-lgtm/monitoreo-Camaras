import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI

# -----------------------------
# 🚀 FastAPI App
# -----------------------------
app = FastAPI()

# -----------------------------
# 📜 Configuración de logging
# -----------------------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)  # crear carpeta logs si no existe

LOG_FILE = os.path.join(LOG_DIR, "app.log")

handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)  # 5 MB, 5 backups
handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
handler.setFormatter(formatter)

logger = logging.getLogger("uvicorn")  # usar el logger principal de FastAPI/Uvicorn
logger.setLevel(logging.INFO)
logger.addHandler(handler)

logger.info("🚀 Aplicación iniciada con logging rotativo")


# -----------------------------
# 🩺 Endpoints de prueba
# -----------------------------
@app.get("/")
async def home():
    logger.info("📄 Endpoint '/' accedido")
    return {"message": "Hola, FastAPI con logging rotativo"} 