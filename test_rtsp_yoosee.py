import cv2
import getpass
import os

# ===========================
# Configuración
# ===========================
IP = "192.168.20.61"   # Cambia si la IP de tu cámara cambia
USER = "admin"
URL_FILE = "camera_url.txt"

# Rutas RTSP comunes en Yoosee (QC-07)
rtsp_paths = [
    "onvif1",
    "ucast/11",
    "stream1",
    "live/ch00_0",
    "live/ch00_1",
    "av0",
    "av1",
]

# ===========================
# Función para probar rutas
# ===========================
def test_paths(password):
    for path in rtsp_paths:
        url = f"rtsp://{USER}:{password}@{IP}:554/{path}"
        print(f"\n🔍 Probando: {url}")

        cap = cv2.VideoCapture(url)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"✅ ÉXITO: Se pudo abrir el stream con ruta '{path}'")

                # Guardar URL en archivo
                with open(URL_FILE, "w") as f:
                    f.write(url)
                print(f"💾 URL guardada en {URL_FILE}")

                # Mostrar vista previa
                cv2.imshow("Vista previa", frame)
                cv2.waitKey(3000)  # 3 segundos
                cv2.destroyAllWindows()

                cap.release()
                return True
        cap.release()
    return False

# ===========================
# Si ya existe un URL guardado, probarlo
# ===========================
if os.path.exists(URL_FILE):
    with open(URL_FILE, "r") as f:
        saved_url = f.read().strip()
    print(f"📂 URL ya guardada: {saved_url}")

    cap = cv2.VideoCapture(saved_url)
    if cap.isOpened():
        print("✅ La URL guardada funciona, usando esa.")
        cap.release()
        exit(0)
    else:
        print("⚠️ La URL guardada ya no funciona, probando de nuevo...")
        cap.release()

# ===========================
# Fase 1: probar sin contraseña
# ===========================
print("🚀 Fase 1: Probando con contraseña vacía...")
if test_paths(""):
    exit(0)

# ===========================
# Fase 2: pedir contraseña al usuario
# ===========================
print("🔑 Ninguna ruta funcionó sin contraseña.")
password = getpass.getpass("Ingresa la contraseña del usuario admin: ")

print("🚀 Fase 2: Probando con la contraseña ingresada...")
if not test_paths(password):
    print("❌ No se pudo conectar con ninguna ruta. Verifica IP, usuario o contraseña.") 