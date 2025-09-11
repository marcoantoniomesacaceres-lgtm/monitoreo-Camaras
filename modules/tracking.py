from ultralytics import YOLO

class Tracker:
    def __init__(self, model_path="yolov8n.pt", tracker="bytetrack.yaml"):
        self.model = YOLO(model_path)
        self.tracker = tracker

    def track(self, frame):
        """Ejecuta detección + tracking y devuelve resultados"""
        results = self.model.track(frame, persist=True, tracker=self.tracker)
        return results