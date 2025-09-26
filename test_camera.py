import cv2

# ⚙️ Configura aquí los datos de tu cámara
IP = "192.168.20.61"   # 👉 reemplaza por la IP encontrada
USER = "admin"          # 👉 cambia si configuraste otro usuario
PASSWORD = ""           # 👉 si la cámara no tiene contraseña, deja vacío

# 🔗 Intenta con las rutas RTSP típicas de Yoosee
urls = [
    f"rtsp://{USER}:{PASSWORD}@{IP}:554/onvif1",
    f"rtsp://{USER}:{PASSWORD}@{IP}:554/ucast/11",
    f"rtsp://{USER}:{PASSWORD}@{IP}:554/stream1",
]

for url in urls:
    print(f"🔍 Probando: {url}")
    cap = cv2.VideoCapture(url)

    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"✅ Conexión exitosa con {url}")
            cv2.imshow("Cámara Yoosee", frame)
            cv2.waitKey(3000)  # muestra la imagen por 3 segundos
            cv2.destroyAllWindows()
            cap.release()
            break
        else:
            print(f"⚠️ Se conectó pero no recibió video en {url}")
            cap.release()
    else:
        print(f"❌ No se pudo conectar con {url}")