"""
Build our own clean training dataset from the Kaggle download.

Why this is needed (see docs/phase1_dataset_report.md):
  * The Kaggle test split has no Bone Loss at all.
  * The same X-ray appears in train AND test (as augmented copies), which
    would make test scores look better than they really are.
  * We only want 4 of the 31 classes, renumbered 0-3.
  * Labels are polygons; we train box detection, so we convert them to boxes.
  * File names contain patient names, so we give every image a neutral name.

What it does:
  1. Group all images by the ORIGINAL X-ray they were made from.
  2. Split the originals 70 / 15 / 15 into train / val / test, so one X-ray
     and its copies always land in exactly one split ("grouped" split), and
     each split gets a fair share of every class ("stratified").
  3. Keep only our 4 classes, renumber them, turn polygons into boxes.
  4. Train keeps all augmented copies; val and test keep one copy per X-ray
     (the highest resolution one), so every X-ray is scored once.
  5. Preprocess each image (ml/preprocess.py) and write YOLO folders + data.yaml.
  6. Optionally repeat train images that contain the rare classes (oversampling).

Usage:
    python -m ml.prepare_dataset --src data --out prepared
    python -m ml.prepare_dataset --src data --dry-run      # only print the numbers
"""
import argparse
import os
import random
import re
import shutil
import struct
from collections import Counter, defaultdict
from pathlib import Path

from ml import CLASS_NAMES

# Original Kaggle class ID -> our new class ID.
ORIGINAL_TO_NEW = {0: 0, 7: 1, 11: 2, 13: 3}
SPLIT_RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
SEED = 42                      # fixed seed = the same split every time
RARE_CLASSES = {1, 3}          # Periapical lesion, Bone Loss (fewest examples)


# ---------------------------------------------------------------- reading the data

def original_name(filename):
    """Roboflow names copies 'NAME_jpg.rf.<hash>.jpg'. Return NAME (the original X-ray)."""
    return re.split(r"_(jpg|jpeg|png)\.rf\.", filename)[0]


def jpeg_size(path):
    """Return (width, height) of a JPEG by reading its header (no image library needed)."""
    with open(path, "rb") as f:
        f.read(2)                                   # skip the JPEG start marker
        while True:
            marker, length = struct.unpack(">2sH", f.read(4))
            if marker[1] in (0xC0, 0xC1, 0xC2):     # "start of frame" holds the size
                f.read(1)
                height, width = struct.unpack(">HH", f.read(4))
                return width, height
            f.read(length - 2)                      # jump to the next block


def polygon_to_box(coords):
    """Turn polygon points [x1, y1, x2, y2, ...] (0-1 range) into a YOLO box (cx, cy, w, h)."""
    xs = [min(max(x, 0.0), 1.0) for x in coords[0::2]]
    ys = [min(max(y, 0.0), 1.0) for y in coords[1::2]]
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
    return (x_min + x_max) / 2, (y_min + y_max) / 2, x_max - x_min, y_max - y_min


def convert_label_line(line):
    """
    Convert one Kaggle label line into our format.
    Returns (new_class, (cx, cy, w, h)), or None for classes we don't use.
    """
    parts = line.split()
    if not parts or int(parts[0]) not in ORIGINAL_TO_NEW:
        return None
    values = [float(v) for v in parts[1:]]
    box = tuple(values) if len(values) == 4 else polygon_to_box(values)
    if box[2] <= 0 or box[3] <= 0:                  # skip broken, zero-size shapes
        return None
    return ORIGINAL_TO_NEW[int(parts[0])], box


def read_labels(label_path):
    """Read a Kaggle label file and return our converted (class, box) list."""
    with open(label_path) as f:
        converted = (convert_label_line(line) for line in f)
        return [item for item in converted if item is not None]


def find_yolo_root(src):
    """Find the Kaggle YOLO folder (the one holding data.yaml and train/valid/test)."""
    expected = Path(src) / "YOLO" / "YOLO"
    if expected.exists():
        return expected
    for yaml_file in Path(src).rglob("data.yaml"):
        if (yaml_file.parent / "train" / "labels").exists():
            return yaml_file.parent
    raise FileNotFoundError(f"No Kaggle YOLO folder found inside {src}")


def collect_originals(yolo_root):
    """
    Read every image of every Kaggle split and group them by original X-ray.
    Returns {original_name: [ {"image": path, "labels": [...]}, ... ]}.
    """
    groups = defaultdict(list)
    for split in ["train", "valid", "test"]:
        image_dir = Path(yolo_root) / split / "images"
        label_dir = Path(yolo_root) / split / "labels"
        for image_path in sorted(image_dir.iterdir()):
            label_path = label_dir / (image_path.stem + ".txt")
            labels = read_labels(label_path) if label_path.exists() else []
            groups[original_name(image_path.name)].append({"image": image_path, "labels": labels})
    return groups


# ---------------------------------------------------------------- splitting

def classes_of(copies):
    """All classes that appear in any copy of one original X-ray."""
    return {cls for copy in copies for cls, _ in copy["labels"]}


def stratify_key(classes, rarity_order):
    """Group an X-ray by the rarest class it contains ('none' if it has none)."""
    for cls in rarity_order:
        if cls in classes:
            return cls
    return "none"


def split_originals(groups, ratios=SPLIT_RATIOS, seed=SEED):
    """Assign each original X-ray to train / val / test. Returns {original: split}."""
    per_class = Counter(cls for copies in groups.values() for cls in classes_of(copies))
    rarity_order = sorted(per_class, key=per_class.get)        # rarest class first

    buckets = defaultdict(list)
    for name in sorted(groups):
        buckets[stratify_key(classes_of(groups[name]), rarity_order)].append(name)

    rng = random.Random(seed)
    assignment = {}
    for key in sorted(buckets, key=str):
        names = buckets[key]
        rng.shuffle(names)
        n_train = round(len(names) * ratios["train"])
        n_val = round(len(names) * ratios["val"])
        for i, name in enumerate(names):
            assignment[name] = "train" if i < n_train else "val" if i < n_train + n_val else "test"
    return assignment


def copies_to_keep(copies, split):
    """Train keeps every augmented copy; val/test keep only the largest-resolution copy."""
    if split == "train":
        return copies
    def area(copy):
        width, height = jpeg_size(copy["image"])
        return width * height
    return [max(copies, key=area)]


# ---------------------------------------------------------------- writing the output

def write_label_file(path, labels):
    """Write labels in YOLO detection format: 'class cx cy w h' per line."""
    with open(path, "w") as f:
        for cls, (cx, cy, w, h) in labels:
            f.write(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")


def write_image(src, dst, preprocess):
    """Copy an image, cleaning it with ml.preprocess when preprocess=True."""
    if preprocess:
        from ml.preprocess import preprocess_file   # needs OpenCV, so only imported here
        if not preprocess_file(src, dst):
            raise ValueError(f"Could not read image {src}")
    else:
        shutil.copyfile(src, dst)


def build_plan(groups, assignment):
    """List every output image: (split, new_name, source_path, labels). New names hide patient names."""
    plan = []
    for index, name in enumerate(sorted(groups)):
        split = assignment[name]
        for copy_no, copy in enumerate(copies_to_keep(groups[name], split)):
            new_name = f"xray_{index:05d}_{copy_no}"
            plan.append((split, new_name, copy["image"], copy["labels"]))
    return plan


def add_oversampling(plan, repeats):
    """Add `repeats` extra copies of every train image that contains a rare class."""
    extra = []
    for split, new_name, src, labels in plan:
        if split == "train" and RARE_CLASSES & {cls for cls, _ in labels}:
            extra += [(split, f"{new_name}_os{r + 1}", src, labels) for r in range(repeats)]
    return plan + extra


def write_dataset(plan, out_dir, preprocess=True):
    """Write images, labels and data.yaml. Oversampled entries reuse the already-written image."""
    out_dir = Path(out_dir)
    for split in SPLIT_RATIOS:
        (out_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (out_dir / split / "labels").mkdir(parents=True, exist_ok=True)
    written = {}
    for i, (split, new_name, src, labels) in enumerate(plan):
        dst = out_dir / split / "images" / f"{new_name}.jpg"
        if src in written:
            shutil.copyfile(written[src], dst)       # oversampled copy: no need to re-process
        else:
            write_image(src, dst, preprocess)
            written[src] = dst
        write_label_file(out_dir / split / "labels" / f"{new_name}.txt", labels)
        if i % 2000 == 0:
            print(f"  written {i}/{len(plan)} images")
    write_data_yaml(out_dir)


def write_data_yaml(out_dir):
    """The small config file that tells YOLO where the data is and what the classes are."""
    names = "\n".join(f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES))
    text = (f"path: {Path(out_dir).resolve().as_posix()}\n"
            f"train: train/images\nval: val/images\ntest: test/images\n\nnames:\n{names}\n")
    (Path(out_dir) / "data.yaml").write_text(text)


# ---------------------------------------------------------------- reporting

def summarize(plan, assignment):
    """Print images and boxes per class for each split, and check there is no leakage."""
    print(f"\n{'split':<6}{'images':>8}{'X-rays':>8}   " +
          "   ".join(f"{n} (imgs/boxes)" for n in CLASS_NAMES))
    for split in SPLIT_RATIOS:
        rows = [p for p in plan if p[0] == split]
        boxes, images = Counter(), Counter()
        for _, _, _, labels in rows:
            classes = [cls for cls, _ in labels]
            boxes.update(classes)
            images.update(set(classes))
        n_xrays = sum(1 for s in assignment.values() if s == split)
        counts = "   ".join(f"{images[c]:>6}/{boxes[c]:<6}".ljust(len(n) + 13) for c, n in enumerate(CLASS_NAMES))
        print(f"{split:<6}{len(rows):>8}{n_xrays:>8}   {counts}")

    sources = defaultdict(set)
    for split, _, src, _ in plan:
        sources[original_name(Path(src).name)].add(split)
    leaks = sum(1 for splits in sources.values() if len(splits) > 1)
    print(f"\nX-rays found in more than one split: {leaks} (must be 0)")
    assert leaks == 0, "Data leakage: an X-ray is in two splits"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", default="data", help="folder where the Kaggle zip was unzipped")
    parser.add_argument("--out", default="prepared", help="where to write the new dataset")
    parser.add_argument("--oversample", type=int, default=1,
                        help="extra copies of train images with rare classes (0 = off)")
    parser.add_argument("--no-preprocess", action="store_true", help="copy images without cleaning them")
    parser.add_argument("--dry-run", action="store_true", help="only print the split numbers")
    args = parser.parse_args()

    groups = collect_originals(find_yolo_root(args.src))
    print(f"Found {sum(len(c) for c in groups.values())} images from {len(groups)} original X-rays")
    assignment = split_originals(groups)
    plan = add_oversampling(build_plan(groups, assignment), args.oversample)
    summarize(plan, assignment)
    if not args.dry_run:
        write_dataset(plan, args.out, preprocess=not args.no_preprocess)
        print(f"\nDone. Dataset written to {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
