import cv2
import time
import logging
import queue
import threading

logger = logging.getLogger("tasks")

class CameraCapture(threading.Thread):
    def __init__(
        self,
        camera_url,
        frame_queue,
        max_failures=10,
        reconnect_delay=5,
        resize_to=(640, 480),
        frame_skip=2,  # 👈 procesa 1 de cada N frames
    ):
        super().__init__(daemon=True)
        self.camera_url = camera_url
        self.frame_queue = frame_queue
        self.max_failures = max_failures
        self.reconnect_delay = reconnect_delay
        self.running = True
        self.cap = None
        self.failures = 0
        self.resize_to = resize_to
        self.frame_skip = frame_skip
        self._frame_count = 0

    def run(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                logger.warning("Cámara no conectada, intentando reconexión...")
                self._connect()

            ret, frame = self.cap.read() if self.cap else (False, None)

            if not ret or frame is None:
                self.failures += 1
                logger.debug(f"Frame inválido ({self.failures}/{self.max_failures})")

                if self.failures >= self.max_failures:
                    logger.error("Cámara fuera de línea")
                    # Señal de error
                    self._safe_put(None)
                    self._reconnect()
                continue

            # ✅ Frame válido
            self.failures = 0
            self._frame_count += 1

            # saltar frames para no atrasar inferencia
            if self.frame_skip > 1 and (self._frame_count % self.frame_skip != 0):
                continue

            if self.resize_to:
                try:
                    frame = cv2.resize(frame, self.resize_to)
                except Exception as e:
                    logger.error(f"Error redimensionando frame: {e}")

            self._safe_put(frame)

        logger.info("🛑 CameraCapture detenido")

    def _connect(self):
        self.cap = cv2.VideoCapture(self.camera_url)
        if not self.cap.isOpened():
            logger.error("No se pudo abrir la cámara.")
            self.cap = None
            time.sleep(self.reconnect_delay)

    def _reconnect(self):
        if self.cap:
            self.cap.release()
        self.cap = None
        time.sleep(self.reconnect_delay)

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()

    def _safe_put(self, frame):
        """ Mete el frame descartando el anterior (cola = último frame solamente)."""
        try:
            while not self.frame_queue.empty():
                self.frame_queue.get_nowait()
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            pass 