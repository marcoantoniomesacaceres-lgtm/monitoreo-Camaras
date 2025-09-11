from pathlib import Path

# Rutas base
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sismonicamaras.db"

# Parámetros de aforo
MAX_CAPACITY = 50

# Configuración de notificaciones (placeholder)
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
EMAIL_SENDER = "alertas@sismonicamaras.com"
EMAIL_PASSWORD = "tu_password"
EMAIL_RECEIVER = "admin@empresa.com"