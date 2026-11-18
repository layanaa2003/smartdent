"""
Evaluate models/best.pt on the held-out test split, on this computer (CPU is fine, about 20 minutes).

It rebuilds exactly the same val/test split as training (ml/prepare_dataset.py, seed 42), so the
test X-rays are ones the model never saw. Needs the Kaggle dataset unzipped in data/.

    .venv\\Scripts\\python scripts\\evaluate_final.py eval_output

Writes eval_output/final_results.json (copied to docs/final_test_results.json for the report):
per-X-ray sensitivity/specificity at the thresholds in models/thresholds.json, a threshold sweep
on val and test, and YOLO's box metrics (precision, recall, mAP50, mAP50-95).
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "eval_output")

from ml import CLASS_NAMES
from ml import prepare_dataset as pdset
from ml.evaluate import image_level_metrics, threshold_sweep, pick_thresholds, match_boxes

t0 = time.time()
yolo_root = pdset.find_yolo_root(ROOT / "data")
pdset.ORIGINAL_TO_NEW.update(pdset.load_class_map(yolo_root))
groups = pdset.collect_originals(yolo_root)
assignment = pdset.split_originals(groups)
plan = [p for p in pdset.build_plan(groups, assignment) if p[0] in ("val", "test")]
prepared = OUT / "prepared"
if not (prepared / "data.yaml").exists():
    pdset.write_dataset(plan, prepared, preprocess=True)
counts = {s: sum(1 for v in assignment.values() if v == s) for s in ("train", "val", "test")}
print("X-rays per split:", counts, flush=True)

from ultralytics import YOLO
model = YOLO(str(ROOT / "models" / "best.pt"))
IMGSZ = int(model.ckpt["train_args"]["imgsz"])
thresholds_by_name = json.loads((ROOT / "models" / "thresholds.json").read_text())
THR = {i: float(thresholds_by_name.get(n, 0.25)) for i, n in enumerate(CLASS_NAMES)}


def read_truth(image_path, width, height):
    label_path = image_path.parent.parent / "labels" / (image_path.stem + ".txt")
    truths = []
    for line in label_path.read_text().splitlines():
        if not line.strip():
            continue
        cls, cx, cy, w, h = line.split()
        cx, cy, w, h = float(cx) * width, float(cy) * height, float(w) * width, float(h) * height
        truths.append((int(cls), (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
    return truths


def predict_split(split):
    found, secs = {}, []
    for image_path in sorted((prepared / split / "images").glob("*.jpg")):
        s = time.perf_counter()
        r = model.predict(str(image_path), conf=0.01, imgsz=IMGSZ, verbose=False)[0]
        secs.append(time.perf_counter() - s)
        h, w = r.orig_shape
        preds = [(int(c), tuple(b), float(sc)) for c, b, sc in
                 zip(r.boxes.cls.tolist(), r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
        found[image_path.name] = (read_truth(image_path, w, h), preds)
    print(f"{split}: {len(found)} X-rays, {sum(secs)/len(secs):.2f} s per X-ray", flush=True)
    return found, sum(secs) / len(secs)


results = {"split_xrays": counts, "imgsz": IMGSZ, "thresholds": thresholds_by_name,
           "train_args": {k: model.ckpt["train_args"].get(k) for k in ("epochs", "batch", "model", "imgsz", "patience")}}

val, _ = predict_split("val")
sweep = threshold_sweep(val)
results["val_sweep"] = sweep
results["val_suggested_thresholds_80"] = {CLASS_NAMES[c]: t for c, t in pick_thresholds(sweep, 0.80).items()}

test, sec = predict_split("test")
results["seconds_per_xray_cpu"] = round(sec, 3)
filtered = {k: (t, [p for p in ps if p[2] >= THR[p[0]]]) for k, (t, ps) in test.items()}
pairs = [({c for c, _ in t}, {c for c, _, _ in p}) for t, p in filtered.values()]
results["test_xray_metrics"] = image_level_metrics(pairs)
results["test_sweep"] = threshold_sweep(test)

box = {}
for cls, name in enumerate(CLASS_NAMES):
    tp = fn = fp = 0
    for t, p in filtered.values():
        a, b, c = match_boxes([x for x in t if x[0] == cls], [x for x in p if x[0] == cls])
        tp += a; fn += b; fp += c
    box[name] = {"true_boxes": tp + fn, "found": tp, "missed": fn, "false_boxes": fp}
results["test_box_counts_at_thresholds"] = box

m = model.val(data=str(prepared / "data.yaml"), split="test", imgsz=IMGSZ, batch=4, plots=False,
              project=str(OUT / "val_runs"), name="test", exist_ok=True, verbose=False)
rows = {}
for i, c in enumerate(m.box.ap_class_index):
    p, r, m50, m5095 = m.box.class_result(i)
    rows[CLASS_NAMES[int(c)]] = {"precision": p, "recall": r, "mAP50": m50, "mAP50-95": m5095}
rows["ALL"] = {"precision": m.box.mp, "recall": m.box.mr, "mAP50": m.box.map50, "mAP50-95": m.box.map}
results["test_box_metrics"] = rows

(OUT / "final_results.json").write_text(json.dumps(results, indent=2, default=float))
print("DONE in", round((time.time() - t0) / 60, 1), "min", flush=True)
