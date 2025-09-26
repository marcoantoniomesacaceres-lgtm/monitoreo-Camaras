import os

CAMERA_URL_FILE = "data/camera_url.txt"

def save_camera_url(url: str):
    os.makedirs(os.path.dirname(CAMERA_URL_FILE), exist_ok=True)
    with open(CAMERA_URL_FILE, "w", encoding="utf-8") as f:
        f.write(url.strip())

def load_camera_url() -> str:
    if os.path.exists(CAMERA_URL_FILE):
        with open(CAMERA_URL_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    # Valor por defecto: webcam local
    return "0"
