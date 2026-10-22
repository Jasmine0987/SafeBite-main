from pathlib import Path
from PIL import Image

WEIGHTS = Path(__file__).parent / "weights" / "panel_yolo.pt"
_model = None

def detect_panel(img: Image.Image) -> Image.Image:
    global _model
    if not WEIGHTS.exists():
        return img
    try:
        if _model is None:
            from ultralytics import YOLO
            _model = YOLO(str(WEIGHTS))
        r = _model.predict(img, imgsz=416, conf=0.25, device="cpu", verbose=False)[0]
        if len(r.boxes) == 0:
            return img
        best = max(r.boxes, key=lambda b: float(b.conf))
        x1, y1, x2, y2 = map(int, best.xyxy[0].tolist())
        return img.crop((x1, y1, x2, y2))
    except Exception:
        return img
