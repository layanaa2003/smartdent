"""
The AI step: from an uploaded X-ray to findings, an annotated image and a summary.

  1. Read the image and clean it with ml.preprocess (the SAME cleaning used in training).
  2. Run the trained YOLOv8 model (models/best.pt) to find boxes.
  3. Turn the boxes into a simple list of findings with confidence scores.
  4. Draw the boxes on the X-ray and write a short plain-language summary.

The model is loaded once and then reused, because loading takes a few seconds.
"""
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

from ml import CLASS_NAMES
from ml.preprocess import preprocess_image

CONFIDENCE_THRESHOLD = 0.25    # ignore boxes the model is less than 25% sure about
IMAGE_SIZE = 640               # must match the size used in training

# One colour per condition (OpenCV uses Blue, Green, Red order).
CLASS_COLOURS = {
    "Caries": (40, 40, 230),             # red
    "Periapical lesion": (0, 200, 255),  # yellow/orange
    "Impacted tooth": (230, 160, 30),    # blue
    "Bone Loss": (60, 200, 60),          # green
}

_model = None
_model_path = None
_lock = threading.Lock()


class ModelNotFound(FileNotFoundError):
    """Raised when models/best.pt is missing."""


def get_model(model_path):
    """Load the YOLO model the first time, then keep it in memory."""
    global _model, _model_path
    model_path = Path(model_path)
    with _lock:
        if _model is None or _model_path != model_path:
            if not model_path.exists():
                raise ModelNotFound(f"Trained model not found at {model_path}")
            from ultralytics import YOLO          # imported here: slow to import
            _model, _model_path = YOLO(str(model_path)), model_path
    return _model


def model_version(model_path):
    """A readable version label: file name + the date the model file was made."""
    path = Path(model_path)
    stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return f"YOLOv8 {path.stem} ({stamp})"


def detect(image_bgr, model):
    """Run the model on one (already preprocessed) image. Returns a list of findings."""
    result = model.predict(image_bgr, conf=CONFIDENCE_THRESHOLD, imgsz=IMAGE_SIZE, verbose=False)[0]
    findings = []
    for cls, box, conf in zip(result.boxes.cls.tolist(), result.boxes.xyxy.tolist(),
                              result.boxes.conf.tolist()):
        findings.append({"label": CLASS_NAMES[int(cls)], "confidence": round(float(conf), 3),
                         "box": [round(v) for v in box]})
    return sorted(findings, key=lambda f: -f["confidence"])


def best_scores(findings):
    """Highest confidence per condition, e.g. {"Caries": 0.71}. Conditions not found are left out."""
    scores = {}
    for f in findings:
        scores[f["label"]] = max(scores.get(f["label"], 0), f["confidence"])
    return scores


def summarize(findings):
    """A short plain-language summary of the findings, for the doctor and the report."""
    if not findings:
        return ("The AI did not detect any of the four conditions it checks for "
                "(caries, periapical lesion, impacted tooth, bone loss).")
    parts = []
    for name in CLASS_NAMES:
        hits = [f for f in findings if f["label"] == name]
        if hits:
            best = max(h["confidence"] for h in hits)
            parts.append(f"{len(hits)} possible {name.lower()} finding(s) (highest confidence {best:.0%})")
    missing = [n.lower() for n in CLASS_NAMES if not any(f["label"] == n for f in findings)]
    text = "The AI flagged " + "; ".join(parts) + "."
    if missing:
        text += " It did not detect " + ", ".join(missing) + "."
    return text


def draw_findings(image_bgr, findings):
    """Return a copy of the image with a coloured box and label for every finding."""
    canvas = image_bgr.copy()
    thickness = max(2, canvas.shape[1] // 600)
    font_scale = max(0.5, canvas.shape[1] / 2000)
    for f in findings:
        x1, y1, x2, y2 = f["box"]
        colour = CLASS_COLOURS.get(f["label"], (255, 255, 255))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, thickness)
        label = f"{f['label']} {f['confidence']:.0%}"
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        top = max(y1 - h - 6, 0)
        cv2.rectangle(canvas, (x1, top), (x1 + w + 6, top + h + 6), colour, -1)
        cv2.putText(canvas, label, (x1 + 3, top + h + 2), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (0, 0, 0), 1, cv2.LINE_AA)
    return canvas


def annotated_name(image_name):
    """File name of the annotated copy of an upload, e.g. abc.jpg -> abc_annotated.jpg."""
    return f"{Path(image_name).stem}_annotated.jpg"


def analyze_file(image_path, model_path):
    """
    Full pipeline for one X-ray file.
    Returns (findings, scores, summary, annotated_path, seconds_taken).
    """
    started = time.perf_counter()
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image {image_path}")
    findings = detect(preprocess_image(image), get_model(model_path))
    annotated_path = Path(image_path).with_name(annotated_name(Path(image_path).name))
    cv2.imwrite(str(annotated_path), draw_findings(image, findings))
    return findings, best_scores(findings), summarize(findings), annotated_path, time.perf_counter() - started
