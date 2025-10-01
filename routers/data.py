import time
import cv2
import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from auth import get_current_user
from modules import storage
import state

router = APIRouter(
    tags=["Data"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/status")
async def get_status(user: dict = Depends(get_current_user)):
    """Devuelve el estado actual del sistema."""
    stats = storage.get_stats()
    return {
        "inside": state.STATE.get("inside", 0),
        "entered": stats.get("entered", 0),
        "exited": stats.get("exited", 0),
        "camera_status": state.CAMERA_STATUS,
        "camera_active": state.CAMERA_ACTIVE,
        "user": user.get("username")
    }

@router.get("/video_feed")
def video_feed():
    """Endpoint de streaming de video con detecciones (formato MJPEG)."""
    def generate_frames():
        while state.CAMERA_ACTIVE:
            if state.frame_queue.empty():
                time.sleep(0.01)
                continue

            frame = state.frame_queue.get()
            if frame is None: # Señal de que la cámara se detuvo
                break

            if state.model:
                results = state.model.track(frame, persist=True, verbose=False)
                processed_frame = results[0].plot()
            else:
                processed_frame = frame # Mostrar frame original si el modelo no cargó

            _, buffer = cv2.imencode(".jpg", processed_frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")

@router.get("/durations")
async def get_durations():
    return storage.get_person_durations()