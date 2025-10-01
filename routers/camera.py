import time
import cv2
from fastapi import APIRouter, Request, Form, Query, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from utils.camera_config import load_camera_url, save_camera_url
from auth import get_current_user, require_role
import state
from tasks import CameraCapture

router = APIRouter(
    tags=["Camera Control"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/camera_url", response_class=PlainTextResponse)
async def get_camera_url():
    """Obtiene la URL de la cámara actualmente configurada."""
    return load_camera_url()

@router.post("/camera_url", response_class=PlainTextResponse, dependencies=[Depends(require_role("admin"))])
async def set_camera_url(url: str = Form(...)):
    """
    Establece una nueva URL para la cámara y la reinicia.
    Solo para administradores.
    """
    save_camera_url(url)
    try:
        if state.capture_thread is not None:
            state.capture_thread.stop()
            time.sleep(0.5)

        camera_url = load_camera_url()
        src = 0 if camera_url.strip() == '0' else camera_url.strip()

        test_cap = cv2.VideoCapture(src)
        time.sleep(1)
        if not test_cap.isOpened():
            state.CAMERA_ACTIVE = False
            state.CAMERA_STATUS = "OFFLINE"
            raise HTTPException(status_code=400, detail="ERROR: No se pudo conectar a la nueva URL de la cámara.")

        # Intentar leer un frame varias veces antes de fallar
        read_attempts = 5
        frame_read_successfully = False
        for _ in range(read_attempts):
            ret, _ = test_cap.read()
            if ret:
                frame_read_successfully = True
                break
            time.sleep(0.2)

        if not frame_read_successfully:
            test_cap.release()
            state.CAMERA_ACTIVE = False
            state.CAMERA_STATUS = "OFFLINE"
            raise HTTPException(status_code=400, detail="ERROR: Se conectó a la cámara pero no se reciben imágenes.")

        test_cap.release()
        state.capture_thread = CameraCapture(camera_url=src, frame_queue=state.frame_queue)
        state.capture_thread.start()
        state.CAMERA_ACTIVE = True
        state.CAMERA_STATUS = "ONLINE"

    except Exception as e:
        state.CAMERA_ACTIVE = False
        state.CAMERA_STATUS = "OFFLINE"
        raise HTTPException(status_code=500, detail=f"ERROR: {e}")

    return "OK"

@router.api_route("/toggle", methods=["GET", "POST"], dependencies=[Depends(require_role("admin"))])
async def toggle_camera(
    request: Request,
    active: bool = Query(None),
    body: dict = Body(None)
):
    """
    Activa o desactiva la captura de la cámara.
    Solo para administradores.
    """
    camera_url = load_camera_url()
    src = 0 if camera_url.strip() == "0" else camera_url.strip()

    if request.method == "GET":
        if active is None:
            return {"success": False, "message": "Falta parámetro 'active' en query", "status": state.CAMERA_STATUS}
    else:  # POST
        if body and "active" in body:
            active = body["active"]
        else:
            return {"success": False, "message": "Falta 'active' en el body", "status": state.CAMERA_STATUS}

    if active:
        if not state.CAMERA_ACTIVE:
            test_cap = cv2.VideoCapture(src)
            time.sleep(1)
            if not test_cap.isOpened():
                state.CAMERA_STATUS = "OFFLINE"
                return {
                    "success": False,
                    "message": "No se pudo activar la cámara.",
                    "status": state.CAMERA_STATUS,
                }
            test_cap.release()
            state.capture_thread = CameraCapture(camera_url=src, frame_queue=state.frame_queue)
            state.capture_thread.start()
            state.CAMERA_ACTIVE = True
            state.CAMERA_STATUS = "ONLINE"
            return {
                "success": True,
                "message": "Cámara activada.",
                "status": state.CAMERA_STATUS,
            }
        else:
            return {
                "success": True,
                "message": "La cámara ya está activa.",
                "status": state.CAMERA_STATUS,
            }
    else:
        if state.CAMERA_ACTIVE and state.capture_thread is not None:
            state.capture_thread.stop()
            state.CAMERA_ACTIVE = False
            state.CAMERA_STATUS = "OFFLINE"
            return {
                "success": True,
                "message": "Cámara desactivada.",
                "status": state.CAMERA_STATUS,
            }
        else:
            return {
                "success": True,
                "message": "La cámara ya está desactivada.",
                "status": state.CAMERA_STATUS,
            }