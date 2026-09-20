"""Local person detector (YOLOv8n). Optional - if ultralytics isn't installed,
detect() returns None and the selected visual AI examines the image."""
from __future__ import annotations

import io

try:
    from ultralytics import YOLO  # type: ignore
    from PIL import Image
    _model = YOLO("yolov8n.pt")  # auto-downloads ~6MB on first use
except Exception:  # noqa: BLE001
    _model = None


def available() -> bool:
    return _model is not None


def detect(frame_jpeg: bytes) -> dict | None:
    """Return {"person": bool, "confidence": float, "bbox": [x1,y1,x2,y2]} or None if unavailable."""
    if _model is None:
        return None
    img = Image.open(io.BytesIO(frame_jpeg)).convert("RGB")
    res = _model.predict(img, classes=[0], conf=0.35, verbose=False)[0]  # class 0 = person
    if len(res.boxes) == 0:
        return {"person": False, "confidence": 0.0, "bbox": None}
    best = max(res.boxes, key=lambda b: float(b.conf[0]))
    return {
        "person": True,
        "confidence": float(best.conf[0]),
        "bbox": [round(float(v)) for v in best.xyxy[0].tolist()],
    }

