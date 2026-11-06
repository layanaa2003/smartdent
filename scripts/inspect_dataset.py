"""
Phase 1: inspect the Kaggle "Dental Disease Panoramic Detection" dataset.

Run from the smartdent folder:
    python scripts/inspect_dataset.py data

It prints, for each split (train / valid / test):
  - how many images and label files there are
  - whether labels are boxes or polygons
  - images and annotations per class for our four target classes
  - how many ORIGINAL radiographs are behind the (augmented) images
  - whether the same original radiograph appears in more than one split
"""
import os
import re
import sys
from collections import Counter, defaultdict

# Original dataset IDs of the four conditions we train on (checked in data.yaml).
TARGET_CLASSES = {0: "Caries", 7: "Periapical lesion", 11: "Impacted tooth", 13: "Bone Loss"}
SPLITS = ["train", "valid", "test"]


def original_name(filename):
    """Roboflow renames each augmented copy 'NAME_jpg.rf.<hash>.jpg'; keep only NAME."""
    return re.split(r"_(jpg|jpeg|png)\.rf\.", filename)[0]


def shape_of(coords):
    """Classify one label line: 'box' (4 corners, axis-aligned), 'quad' (4 corners, rotated) or 'polygon'."""
    if len(coords) != 8:
        return "polygon"
    xs = {round(x, 4) for x in coords[0::2]}
    ys = {round(y, 4) for y in coords[1::2]}
    return "box" if len(xs) == 2 and len(ys) == 2 else "quad"


def inspect_split(label_dir):
    """Count annotations, images and label shapes per target class in one split."""
    annotations, images, originals = Counter(), Counter(), defaultdict(set)
    shapes = defaultdict(Counter)
    all_originals = set()
    files = os.listdir(label_dir)
    for name in files:
        source = original_name(name)
        all_originals.add(source)
        classes_in_image = set()
        with open(os.path.join(label_dir, name)) as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                cls = int(parts[0])
                if cls not in TARGET_CLASSES:
                    continue
                annotations[cls] += 1
                shapes[cls][shape_of([float(v) for v in parts[1:]])] += 1
                classes_in_image.add(cls)
                originals[cls].add(source)
        for cls in classes_in_image:
            images[cls] += 1
    return len(files), all_originals, annotations, images, originals, shapes


def main(data_root):
    yolo_root = os.path.join(data_root, "YOLO", "YOLO")
    originals_per_split = {}
    for split in SPLITS:
        n_files, all_orig, ann, img, orig, shapes = inspect_split(os.path.join(yolo_root, split, "labels"))
        originals_per_split[split] = all_orig
        print(f"\n=== {split}: {n_files} images from {len(all_orig)} original radiographs ===")
        for cls, label in TARGET_CLASSES.items():
            print(f"  {label:<18} images={img[cls]:>5}  annotations={ann[cls]:>6}  "
                  f"originals={len(orig[cls]):>5}  shapes={dict(shapes[cls])}")

    print("\n=== Same original radiograph in two splits (data leakage) ===")
    for a, b in [("train", "valid"), ("train", "test"), ("valid", "test")]:
        print(f"  {a} & {b}: {len(originals_per_split[a] & originals_per_split[b])}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data")
