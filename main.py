from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import cv2
from ultralytics import YOLO
from modules import storage, alerts, notifications
from reports.daily_report import generate_daily_report
from reports.weekly_report import generate_weekly_report
from reports.monthly_report import generate_monthly_report

app = FastAPI()
storage.init_db()

# Estado global
STATE = {"inside": 0, "entered": 0, "exited": 0}
CAMERA_ACTIVE = False

# Configuración de templates
templates = Jinja2Templates(directory="dashboard/templates")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

# Cargar modelo YOLOv8
model = YOLO("yolov8n.pt")

# Historial de posiciones por ID para saber dirección de cruce
last_positions = {}

# -----------------------------
# 🚀 Páginas principales
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "state": STATE, "camera_active": CAMERA_ACTIVE},
    )

@app.get("/status")
async def get_status():
    return STATE

# 🚀 Endpoint de tiempos
@app.get("/durations")
async def get_durations():
    return storage.get_person_durations()

# -----------------------------
# 📊 Reportes
# -----------------------------
@app.get("/reports/daily")
async def daily_report():
    filepath = generate_daily_report()
    return FileResponse(filepath, media_type="text/csv", filename="daily_report.csv")

@app.get("/reports/weekly")
async def weekly_report():
    filepath = generate_weekly_report()
    return FileResponse(filepath, media_type="text/csv", filename="weekly_report.csv")

@app.get("/reports/monthly")
async def monthly_report():
    filepath = generate_monthly_report()
    return FileResponse(filepath, media_type="text/csv", filename="monthly_report.csv")

# -----------------------------
# 📷 Video con YOLOv8 + Tracking
# -----------------------------
def generate_video():
    global CAMERA_ACTIVE, last_positions

    cap = cv2.VideoCapture(0)  # 👈 Cambia "0" por URL de cámara IP si usas una remota
    line_y = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) // 2)  # línea virtual horizontal

    while CAMERA_ACTIVE:
        success, frame = cap.read()
        if not success:
            break

        results = model.track(frame, persist=True, stream=True)

        for r in results:
            if r.boxes.id is None:
                continue
            for box in r.boxes:
                cls = int(box.cls[0])
                if model.names[cls] != "person":
                    continue

                person_id = int(box.id[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2  # centro del bbox

                # Dibujar detección
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f"ID {person_id}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

                # Lógica de cruce
                if person_id in last_positions:
                    prev_y = last_positions[person_id]
                    # De abajo hacia arriba = entrada
                    if prev_y > line_y and cy <= line_y:
                        STATE["entered"] += 1
                        STATE["inside"] += 1
                        storage.save_event("entered", person_id)
                    # De arriba hacia abajo = salida
                    elif prev_y < line_y and cy >= line_y:
                        STATE["exited"] += 1
                        STATE["inside"] = max(0, STATE["inside"] - 1)
                        storage.save_event("exited", person_id)

                last_positions[person_id] = cy

        # Dibujar línea virtual
        cv2.line(frame, (0, line_y), (frame.shape[1], line_y), (255, 0, 0), 2)

        _, buffer = cv2.imencode(".jpg", frame)
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )

    cap.release()

@app.get("/video")
async def video_feed():
    if not CAMERA_ACTIVE:
        return JSONResponse({"error": "Cámara apagada"})
    return StreamingResponse(
        generate_video(), media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/toggle_camera")
async def toggle_camera():
    global CAMERA_ACTIVE
    CAMERA_ACTIVE = not CAMERA_ACTIVE
    return {"camera_active": CAMERA_ACTIVE}