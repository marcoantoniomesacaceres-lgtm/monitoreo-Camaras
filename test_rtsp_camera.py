import cv2

url = "rtsp://admin:admin@192.168.20.93:8080"

print(f"Intentando abrir cámara en {url} ...")

cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("❌ No se pudo abrir la cámara")
else:
    print("✅ Cámara abierta correctamente")
    ret, frame = cap.read()
    if ret:
        print("✅ Se recibió un frame:", frame.shape)
    else:
        print("⚠️ Se abrió pero no se reciben frames")
    cap.release()