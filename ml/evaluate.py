"""
Extra evaluation that YOLO does not report by itself.

YOLO's own validation gives precision, recall, mAP and a confusion matrix per
box. Dentists also think per X-ray: "does this X-ray show caries or not?".
This file computes, per class and per X-ray:

  sensitivity = of the X-rays that HAVE the condition, how many did we flag?
  specificity = of the X-rays that DON'T have it, how many did we leave clean?
  accuracy    = how many X-rays we got right overall (yes/no) for that class

It also ranks X-rays by mistakes (missed boxes + false boxes) for error analysis.

Boxes are (x1, y1, x2, y2) in pixels. Only plain Python, so it is easy to test.
"""
from ml import CLASS_NAMES

IOU_MATCH = 0.5   # a prediction "finds" a true box if they overlap at least 50%


def iou(a, b):
    """Intersection over Union of two boxes: overlap area / combined area (0 to 1)."""
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    overlap = width * height
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union > 0 else 0.0


def match_boxes(truths, predictions, iou_threshold=IOU_MATCH):
    """
    Match predicted boxes to true boxes of the same class.
    truths:      [(cls, box), ...]
    predictions: [(cls, box, confidence), ...]
    Returns (true_positives, missed, false_alarms) as counts.
    """
    unmatched = list(truths)
    true_positives = false_alarms = 0
    # Most confident predictions get first pick of the true boxes.
    for cls, box, _ in sorted(predictions, key=lambda p: -p[2]):
        best = max((t for t in unmatched if t[0] == cls), key=lambda t: iou(t[1], box), default=None)
        if best is not None and iou(best[1], box) >= iou_threshold:
            unmatched.remove(best)
            true_positives += 1
        else:
            false_alarms += 1
    return true_positives, len(unmatched), false_alarms


def image_level_metrics(results, n_classes=len(CLASS_NAMES)):
    """
    results: one (true_classes, predicted_classes) pair of sets per X-ray.
    Returns {class_name: {"sensitivity", "specificity", "accuracy", "tp", "fn", "tn", "fp"}}.
    """
    metrics = {}
    for cls in range(n_classes):
        tp = fn = tn = fp = 0
        for truth, predicted in results:
            has, flagged = cls in truth, cls in predicted
            tp += has and flagged
            fn += has and not flagged
            fp += flagged and not has
            tn += not has and not flagged
        total = tp + fn + tn + fp
        metrics[CLASS_NAMES[cls]] = {
            "sensitivity": tp / (tp + fn) if tp + fn else None,
            "specificity": tn / (tn + fp) if tn + fp else None,
            "accuracy": (tp + tn) / total if total else None,
            "tp": tp, "fn": fn, "tn": tn, "fp": fp,
        }
    return metrics


def worst_images(per_image, top=12):
    """
    per_image: {image_name: (truths, predictions)} as in match_boxes.
    Returns the `top` images with the most mistakes: [(name, missed, false_alarms), ...].
    """
    scored = []
    for name, (truths, predictions) in per_image.items():
        _, missed, false_alarms = match_boxes(truths, predictions)
        scored.append((name, missed, false_alarms))
    return sorted(scored, key=lambda s: -(s[1] + s[2]))[:top]
