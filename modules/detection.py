from ultralytics import YOLO

class Detector:
    def __init__(self, model_path="yolov8n.pt"):
        self.model = YOLO(model_path)

    def detect(self, frame):
        """Devuelve detecciones crudas"""
        results = self.model(frame)
        return results